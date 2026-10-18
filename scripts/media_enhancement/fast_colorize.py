#!/usr/bin/env python3
"""Process at most one current grayscale still without waiting behind GPU jobs."""

# ruff: noqa: E402
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

sys.path = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from PIL import Image

from app.utils.enhancement_pipeline import index_path, resolve_pool
from scripts.feed_tv.core import lock, read, write
from scripts.media_enhancement.colorize import grayscale_metrics
from scripts.media_enhancement.colorize_policy import eligible
from scripts.media_enhancement.integrate import capture_max_age, publish
from scripts.media_enhancement.queue import ROOT, enqueue, run_one


def current_capture(directory, camera, now, max_age):
    """Choose by recorded capture time, excluding symlinks and future captures."""
    if directory.is_symlink():
        return None
    candidates = []
    for path in directory.glob("*.png.clean.png"):
        match = re.fullmatch(
            re.escape(camera) + r"_(\d{14})\.png\.clean\.png", path.name
        )
        if not match or path.is_symlink():
            continue
        try:
            stamp = (
                dt.datetime.strptime(match[1], "%Y%m%d%H%M%S")
                .replace(tzinfo=dt.timezone.utc)
                .timestamp()
            )
        except ValueError:
            continue
        if 0 <= now - stamp <= max_age:
            candidates.append((stamp, path))
    return max(candidates) if candidates else None


def tick(templates, data, root=ROOT, now=None, worker=None):
    """Use saved captures only; retain queue locks, capacity and retry backoff."""
    now = time.time() if now is None else now
    worker = worker or run_one
    outcomes = {}
    processed = 0
    with lock(root, "fast-colorize"):
        # Oldest displayed camera gets first access if more cameras opt in.
        ordered = sorted(
            templates.items(),
            key=lambda item: (
                read(index_path(item[0], root)).get("captured_at", 0),
                item[0],
            ),
        )
        for camera, settings in ordered:
            if (
                settings.get("enhancement_recipe") != "neural-colorize"
                or not settings.get("enhancement_enabled")
                or not settings.get("enhancement_display")
            ):
                continue
            try:
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", camera):
                    raise ValueError("invalid_camera")
                pool = settings.get("enhancement_pool")
                resolve_pool(pool, "neural-colorize")
                candidate = current_capture(
                    data / camera, camera, now, capture_max_age(settings)
                )
                if candidate is None:
                    outcomes[camera] = "waiting_for_current_capture"
                    continue
                stamp, source = candidate
                if not eligible(camera, stamp):
                    outcomes[camera] = "outside_daylight_window"
                    continue
                with Image.open(source) as image:
                    if image.width * image.height > 4_200_000:
                        raise ValueError("colorizer_geometry_budget")
                    grayscale_metrics(np.asarray(image.convert("RGB")))
                identifier = enqueue(
                    root, source, camera, stamp, "neural-colorize", "still", pool=pool
                )
                row = read(root / identifier / "job.json")
                if row.get("state") == "ready":
                    outcomes[camera] = (
                        "display_ready"
                        if publish(camera, settings, source, identifier, root)
                        else "display_rejected"
                    )
                    continue
                if processed:
                    outcomes[camera] = "processing_budget"
                    continue
                if row.get("state") not in {"queued", "retry"}:
                    outcomes[camera] = row.get("state", "unavailable")
                    continue
                if row.get("retry_at", 0) > now:
                    outcomes[camera] = "retry_backoff"
                    continue
                processed += 1
                try:
                    state = worker(root, job_id=identifier)
                except SystemExit as error:
                    if error.code != 0:
                        raise
                    outcomes[camera] = "worker_busy"
                    break
                outcomes[camera] = state
                if state == "ready":
                    outcomes[camera] = (
                        "display_ready"
                        if publish(camera, settings, source, identifier, root)
                        else "display_rejected"
                    )
            except (OSError, ValueError, TypeError, KeyError) as error:
                # Fixed reasons only; never report arbitrary worker exception text.
                reason = str(error)
                outcomes[camera] = (
                    reason
                    if reason
                    in {
                        "original_already_has_color",
                        "colorizer_insufficient_visible_light",
                        "colorizer_geometry_budget",
                        "storage_reserve",
                        "library_full",
                        "queue_full",
                    }
                    else "unavailable_original_preserved"
                )
        result = {"checked_at": now, "processed": processed, "cameras": outcomes}
        write(root / "fast-colorize-status.json", result)
        return result


def main():
    from app.config import SCREENSHOT_DIRECTORY
    from app.utils.template_manager import get_templates

    print(json.dumps(tick(get_templates(), Path(SCREENSHOT_DIRECTORY))))


if __name__ == "__main__":
    main()
