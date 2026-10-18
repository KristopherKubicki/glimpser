#!/usr/bin/env python3
"""Rate-limited repair for templates with stale LLM captions."""

from __future__ import annotations

import argparse
import logging
import math
import time
from dataclasses import dataclass

import psutil

from app.utils.scheduling import (
    _caption_refresh_due,
    _template_timestamp,
    update_camera,
)
from app.utils.template_manager import get_template, get_templates
from app.viewer_policy import ARCHIVE_GROUPS

DEFAULT_SKIP_GROUPS = ARCHIVE_GROUPS | {"source-dead", "expected-offline"}


@dataclass(frozen=True)
class CaptionBackfillCandidate:
    """Template selected for a stale-caption refresh."""

    name: str
    lag_hours: float
    groups: str
    last_screenshot_time: str
    last_caption_time: str


def _group_set(groups: str | None) -> set[str]:
    """Return normalized group names from a comma-separated group string."""

    return {group.strip().lower() for group in str(groups or "").split(",") if group}


def caption_lag_hours(template: dict) -> float | None:
    """Return screenshot-to-caption lag in hours, or infinity for no caption."""

    shot_time = _template_timestamp(template.get("last_screenshot_time"))
    if shot_time is None:
        return None
    caption_time = _template_timestamp(template.get("last_caption_time"))
    if caption_time is None:
        return math.inf
    return (shot_time - caption_time).total_seconds() / 3600


def select_stale_caption_candidates(
    templates: dict[str, dict],
    *,
    include_groups: set[str] | None = None,
    skip_groups: set[str] | None = None,
    min_lag_hours: float = 24.0,
    include_failed: bool = False,
) -> list[CaptionBackfillCandidate]:
    """Return active templates whose captions are stale enough to backfill."""

    include_groups = {group.lower() for group in include_groups or set()}
    skip_groups = {group.lower() for group in (skip_groups or DEFAULT_SKIP_GROUPS)}
    candidates: list[CaptionBackfillCandidate] = []

    for name, template in templates.items():
        groups = _group_set(template.get("groups"))
        if include_groups and not groups.intersection(include_groups):
            continue
        if groups.intersection(skip_groups):
            continue
        if not include_failed and (
            template.get("capture_failed") or template.get("offline_since")
        ):
            continue
        lag_hours = caption_lag_hours(template)
        if lag_hours is None or lag_hours < min_lag_hours:
            continue
        if not _caption_refresh_due(template):
            continue
        candidates.append(
            CaptionBackfillCandidate(
                name=name,
                lag_hours=lag_hours,
                groups=str(template.get("groups") or ""),
                last_screenshot_time=str(template.get("last_screenshot_time") or ""),
                last_caption_time=str(template.get("last_caption_time") or ""),
            )
        )

    candidates.sort(key=lambda candidate: candidate.lag_hours, reverse=True)
    return candidates


def _parse_group_csv(value: str) -> set[str]:
    """Parse comma-separated group names."""

    return {group.strip().lower() for group in value.split(",") if group.strip()}


def _format_lag(hours: float) -> str:
    """Return compact lag text."""

    if math.isinf(hours):
        return "no-caption-time"
    return f"{hours:.1f}h"


def wait_for_cpu_capacity(
    *,
    max_cpu_percent: float,
    wait_seconds: float,
    attempts: int,
) -> bool:
    """Wait for enough CPU headroom before starting another refresh."""

    if max_cpu_percent <= 0:
        return True
    for attempt in range(max(1, attempts)):
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent <= max_cpu_percent:
            return True
        remaining = attempts - attempt - 1
        print(
            f"CPU {cpu_percent:.1f}% exceeds {max_cpu_percent:.1f}%; "
            f"waiting {wait_seconds:.0f}s ({remaining} attempts left)",
            flush=True,
        )
        if remaining > 0 and wait_seconds > 0:
            time.sleep(wait_seconds)
    return False


def run_backfill(args: argparse.Namespace) -> int:
    """Run a bounded stale-caption backfill."""

    templates = get_templates()
    candidates = select_stale_caption_candidates(
        templates,
        include_groups=_parse_group_csv(args.groups) if args.groups else None,
        skip_groups=_parse_group_csv(args.skip_groups),
        min_lag_hours=args.min_lag_hours,
        include_failed=args.include_failed,
    )
    if args.limit > 0:
        candidates = candidates[: args.limit]

    if not candidates:
        print("No stale-caption candidates matched.")
        return 0

    for candidate in candidates:
        print(
            f"{candidate.name}\tlag={_format_lag(candidate.lag_hours)}"
            f"\tgroups={candidate.groups or '-'}"
            f"\tshot={candidate.last_screenshot_time or '-'}"
            f"\tcaption={candidate.last_caption_time or '-'}"
        )

    if args.dry_run:
        return 0

    refreshed = 0
    failed = 0
    for index, candidate in enumerate(candidates, start=1):
        if not wait_for_cpu_capacity(
            max_cpu_percent=args.max_cpu_percent,
            wait_seconds=args.cpu_wait_seconds,
            attempts=args.cpu_wait_attempts,
        ):
            print("CPU stayed above threshold; stopping backfill.")
            failed += len(candidates) - index + 1
            break
        before = get_template(candidate.name)
        before_caption_time = before.get("last_caption_time")
        print(f"[{index}/{len(candidates)}] refreshing {candidate.name}", flush=True)
        try:
            update_camera(candidate.name, before)
        except Exception:
            logging.exception("Backfill failed for %s", candidate.name)
            failed += 1
            continue
        after = get_template(candidate.name)
        after_caption_time = after.get("last_caption_time")
        if after_caption_time and after_caption_time != before_caption_time:
            refreshed += 1
            print(f"  caption refreshed: {after_caption_time}", flush=True)
        else:
            failed += 1
            print("  caption unchanged", flush=True)
        if args.delay_seconds > 0 and index < len(candidates):
            time.sleep(args.delay_seconds)

    print(f"Backfill complete: refreshed={refreshed} unchanged_or_failed={failed}")
    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5, help="max templates to refresh")
    parser.add_argument(
        "--groups",
        default="",
        help="only include these comma-separated groups, e.g. site-one,site-two",
    )
    parser.add_argument(
        "--skip-groups",
        default=",".join(sorted(DEFAULT_SKIP_GROUPS)),
        help="comma-separated groups to skip",
    )
    parser.add_argument(
        "--min-lag-hours",
        type=float,
        default=24.0,
        help="minimum screenshot-to-caption lag before refresh",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=5.0,
        help="delay between refreshes",
    )
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="include templates currently marked failed/offline",
    )
    parser.add_argument(
        "--max-cpu-percent",
        type=float,
        default=75.0,
        help="wait/stop when system CPU is above this threshold; <=0 disables",
    )
    parser.add_argument(
        "--cpu-wait-seconds",
        type=float,
        default=30.0,
        help="seconds to wait between CPU threshold checks",
    )
    parser.add_argument(
        "--cpu-wait-attempts",
        type=int,
        default=10,
        help="number of CPU threshold checks before stopping",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list candidates without refreshing them",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
    return run_backfill(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
