#!/usr/bin/env python3
"""Bounded camera opt-in dispatcher and display publisher; run on capture host."""

# Queue module must not shadow the standard library during app imports.
# ruff: noqa: E402
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time
from pathlib import Path

sys.path = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image, ImageDraw, ImageFont

from app.utils.enhancement_pipeline import (
    RECIPES,
    ROOT,
    file_hash,
    index_path,
    resolve_pool,
)
from app.utils.enhancement_review import asset
from scripts.feed_tv.core import lock, read, write
from scripts.media_enhancement.archive import archive_completed
from scripts.media_enhancement.queue import enqueue, run_one, supersede_pending


def capture_max_age(settings):
    """Allow one scheduled capture interval plus grace, capped at one hour."""
    try:
        minutes = float(settings.get("frequency", 0))
    except (ValueError, TypeError, OverflowError):
        return 900
    if not math.isfinite(minutes) or minutes <= 0:
        return 900
    return min(3600, max(900, minutes * 60 + 300))


def prune_display_cache(root, now):
    """Remove only old, unreferenced badges; preserve sources and review images.

    Call under the shared display-publish lock to exclude all publishers.
    A one-hour grace period protects recently served URLs and in-flight readers.
    Malformed indexes hold cleanup rather than guessing what is still referenced.
    """
    referenced = set()
    for pointer in (root / "live-index").glob("*.json"):
        if pointer.is_symlink():
            return 0
        row = read(pointer)
        if not isinstance(row, dict):
            return 0
        identifier = row.get("id", "")
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[a-f0-9]{64}", identifier
        ):
            return 0
        referenced.add(identifier)
    reclaimed = 0
    for folder in root.iterdir():
        if folder.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}", folder.name):
            continue
        if folder.name in referenced:
            continue
        display = folder / "display.png"
        if display.is_symlink() or not display.is_file():
            continue
        stat = display.stat()
        if now - stat.st_mtime < 3600:
            continue
        # These two retained files are the recovery inputs for this cache.
        if not (folder / "source").is_file() or not (folder / "enhanced.png").is_file():
            continue
        display.unlink()
        reclaimed += stat.st_size
    return reclaimed


def publish(camera, settings, source, job_id, root=ROOT):
    """Publish atomically across dispatchers; contention preserves the last view."""
    try:
        with lock(root, "display-publish"):
            return _publish_locked(camera, settings, source, job_id, root)
    except SystemExit as error:
        if error.code != 0:
            raise
        return False


def _publish_locked(camera, settings, source, job_id, root):
    """Validate and publish while holding the shared display/maintenance lock."""
    folder = root / job_id
    row = read(folder / "job.json")
    pool = resolve_pool(settings["enhancement_pool"], settings["enhancement_recipe"])
    if (
        row.get("state") != "ready"
        or (row.get("processing") or {}).get("review_only") is True
        or row.get("kind") != "still"
        or row.get("camera") != camera
        or row.get("sha256") != file_hash(source)
        or row.get("profile") != settings["enhancement_recipe"]
        or row.get("pool") != settings["enhancement_pool"]
        or row.get("scope") != pool["scope"]
        or (row.get("quality_review") or {}).get("decision") == "reject"
    ):
        return False
    if row.get("profile") == "neural-colorize":
        from scripts.media_enhancement.colorize_policy import eligible

        if row.get("processing", {}).get("color_inferred") is not True or not eligible(
            camera, row.get("captured_at")
        ):
            return False
    verified = asset(job_id, "enhanced", root)
    if not verified:
        return False
    display = folder / "display.png"
    pointer = index_path(camera, root)
    # A slow older worker must never roll a newer display back. Recipe or pool
    # changes can intentionally replace a derivative of the same saved capture.
    prior = read(pointer)
    stamp = row.get("captured_at")
    if type(stamp) not in (int, float) or not math.isfinite(stamp):
        return False
    previous_stamp = prior.get("captured_at")
    if (
        prior.get("camera") == camera
        and prior.get("profile") == row["profile"]
        and prior.get("pool") == row["pool"]
        and prior.get("scope") == row["scope"]
        and type(previous_stamp) in (int, float)
        and math.isfinite(previous_stamp)
        and previous_stamp > stamp
    ):
        return False
    # Reuse a valid artifact; do not encode the same large image every tick.
    if (
        prior.get("id") == job_id
        and display.is_file()
        and prior.get("display_hash") == file_hash(display, 64 * 1024**2)
    ):
        return True
    with Image.open(verified[0]) as image:
        if image.width * image.height > 4_200_000:
            return False
        picture = image.convert("RGB")
    label = {
        "night-adaptive": "Night shadows",
        "neural-native": "AI restored",
        "neural-colorize": "AI color / inferred",
        "neural-lowlight": "AI restored + lighting",
        "neural-2x": "AI restored / 2x",
        "gentle": "Denoised",
    }[row["profile"]]
    if (
        row["profile"] == "night-adaptive"
        and row.get("processing", {}).get("mode") == "multiframe"
    ):
        label = "Multiframe + night shadows"
    if (
        row["profile"] == "neural-lowlight"
        and (row.get("processing", {}).get("lighting") or {}).get("state") == "held"
    ):
        label = "AI restored / lighting held"
    # Badge is added after inference, never fed back into capture history.
    try:
        font = ImageFont.load_default(size=max(10, round(min(picture.size) * 0.018)))
    except TypeError:  # Older supported Pillow releases have only a fixed font.
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(picture)
    box = draw.textbbox((0, 0), label, font=font)
    width, height = box[2] - box[0] + 16, box[3] - box[1] + 12
    x, y = max(0, picture.width - width - 8), max(0, picture.height - height - 8)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=5, fill=(8, 18, 28))
    draw.text((x + 8, y + 6 - box[1]), label, font=font, fill=(212, 238, 229))
    temporary = folder / "display.new.png"
    picture.save(temporary)
    os.replace(temporary, display)
    pointer.parent.mkdir(mode=0o700, exist_ok=True)
    write(
        pointer,
        dict(
            id=job_id,
            camera=camera,
            profile=row["profile"],
            pool=row["pool"],
            scope=row["scope"],
            source_hash=row["sha256"],
            captured_at=row["captured_at"],
            display_hash=file_hash(display, 64 * 1024**2),
        ),
    )
    return True


def sync(templates, data, root=ROOT, now=None):
    """At most three submissions/tick; one current source per opted-in camera."""
    now = time.time() if now is None else now
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    outcomes, admitted = {}, 0
    with lock(root, "integrate"):
        try:
            with lock(root, "display-publish"):
                maintenance_errors = {}
                try:
                    reclaimed = prune_display_cache(root, now)
                except (OSError, ValueError, TypeError, AttributeError) as error:
                    reclaimed = 0
                    maintenance_errors["display_cache"] = type(error).__name__
                try:
                    archive_status = archive_completed(root, now)
                except (OSError, ValueError, TypeError, AttributeError) as error:
                    # Maintenance must not prevent unrelated cameras from progressing.
                    # A completed atomic move remains readable in the archive even if
                    # recording its receipt fails; report uncertainty, never delete it.
                    archive_status = {"state": "error", "reason": type(error).__name__}
                    maintenance_errors["archive"] = type(error).__name__
        except SystemExit as error:
            if error.code != 0:
                raise
            reclaimed = 0
            archive_status = {"state": "held", "reason": "display_publication_busy"}
            maintenance_errors = {"display_cache": "publication_busy"}
        jobs = [read(p) for p in root.glob("*/job.json")]
        # Give never-served and least-recently admitted cameras first access.
        # Dictionary/database order must not let busy cameras starve the estate.
        last_admitted = {}
        for job in jobs:
            key = (job.get("camera"), job.get("pool"), job.get("profile"))
            last_admitted[key] = max(last_admitted.get(key, 0), job.get("queued_at", 0))
        ordered = sorted(
            templates.items(),
            key=lambda item: (
                last_admitted.get(
                    (
                        item[0],
                        item[1].get("enhancement_pool"),
                        item[1].get("enhancement_recipe"),
                    ),
                    0,
                ),
                item[0],
            ),
        )
        for camera, settings in ordered:
            if not settings.get("enhancement_enabled"):
                continue
            try:
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", camera):
                    raise ValueError("invalid_camera")
                profile, pool = (
                    settings.get("enhancement_recipe"),
                    settings.get("enhancement_pool"),
                )
                if profile not in RECIPES:
                    raise ValueError("unsupported_recipe")
                resolve_pool(pool, profile)
                directory = data / camera
                if directory.is_symlink():
                    raise ValueError("symlink_source")
                candidates = []
                for p in directory.glob("*.png.clean.png"):
                    match = re.fullmatch(
                        re.escape(camera) + r"_(\d{14})\.png\.clean\.png", p.name
                    )
                    if match and not p.is_symlink():
                        stamp = (
                            dt.datetime.strptime(match[1], "%Y%m%d%H%M%S")
                            .replace(tzinfo=dt.timezone.utc)
                            .timestamp()
                        )
                        if 0 <= now - stamp <= capture_max_age(settings):
                            candidates.append((stamp, p))
                if not candidates:
                    outcomes[camera] = "waiting_for_current_clean_capture"
                    continue
                stamp, source = max(candidates)
                if profile == "neural-colorize":
                    from scripts.media_enhancement.colorize_policy import eligible

                    if not eligible(camera, stamp):
                        outcomes[camera] = (
                            "colorization_daylight_gate_original_preserved"
                        )
                        continue
                digest = file_hash(source)
                # A newer camera capture makes pending dashboard work obsolete.
                # Retain originals/metadata, but spend GPU time on the current frame.
                supersede_pending(root, camera, pool, profile, stamp)
                prior = next(
                    (
                        r
                        for r in jobs
                        if r.get("camera") == camera
                        and r.get("sha256") == digest
                        and r.get("profile") == profile
                        and r.get("pool") == pool
                        and r.get("captured_at") == stamp
                    ),
                    None,
                )
                if prior:
                    if (
                        settings.get("enhancement_display")
                        and prior.get("state") == "ready"
                    ):
                        outcomes[camera] = (
                            "display_ready"
                            if publish(camera, settings, source, prior["id"], root)
                            else "display_rejected"
                        )
                    else:
                        outcomes[camera] = prior.get("state", "unknown")
                elif admitted < 3:
                    # Restore expensive enlarged frames only inside their budget.
                    with Image.open(source) as image:
                        if image.width * image.height > (
                            1_050_000 if profile == "neural-2x" else 4_200_000
                        ):
                            raise ValueError("recipe_pixel_budget")
                    if profile == "night-adaptive":
                        from scripts.media_enhancement.night_live import produce

                        identifier = produce(
                            root,
                            source,
                            camera,
                            stamp,
                            pool,
                            now,
                            max_age=capture_max_age(settings),
                        )
                        if identifier is None:
                            outcomes[camera] = "already_lit_original_preserved"
                            continue
                        admitted += 1
                        outcomes[camera] = (
                            "display_ready"
                            if settings.get("enhancement_display")
                            and publish(camera, settings, source, identifier, root)
                            else "ready"
                        )
                        continue
                    enqueue(root, source, camera, stamp, profile, "still", pool=pool)
                    admitted += 1
                    outcomes[camera] = "queued"
                else:
                    outcomes[camera] = "submission_budget"
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                outcomes[camera] = "unavailable_original_preserved"
        write(
            root / "integration-status.json",
            {
                "checked_at": now,
                "cameras": outcomes,
                "display_cache_reclaimed_bytes": reclaimed,
                "archive": archive_status,
                "maintenance_errors": maintenance_errors,
            },
        )
    return outcomes


def drain(templates, data, root=ROOT, worker=None):
    """Process up to three jobs, publishing after each; stop on deferral/failure."""
    worker = worker or run_one
    outcomes = sync(templates, data, root)
    for _ in range(3):
        state = worker(root)
        outcomes = sync(templates, data, root)
        if state != "ready":
            break
    return outcomes


def main():
    from app.config import SCREENSHOT_DIRECTORY
    from app.utils.template_manager import get_templates

    parser = argparse.ArgumentParser()
    parser.add_argument("--drain", action="store_true")
    args = parser.parse_args()
    action = drain if args.drain else sync
    print(json.dumps(action(get_templates(), Path(SCREENSHOT_DIRECTORY))))


if __name__ == "__main__":
    main()
