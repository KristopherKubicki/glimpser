"""Bounded timelapses from accepted screenshots, without capturing or encoding video."""

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from PIL import Image, ImageOps, UnidentifiedImageError

from app import config
from app.utils.source_freshness import source_freshness
from app.utils.template_manager import get_template
from app.utils.validators import validate_template_name
from app.viewer_policy import VIEWER_CONFIG

MAX_FRAMES = 24
FRAME_MS = 600
MAX_CANDIDATES = 48


def activity_score(previous, current):
    """Rank local motion plus a modest contribution from daylight changes."""
    if previous is None:
        return 0.0
    deltas = [b - a for a, b in zip(previous.getdata(), current.getdata())]
    exposure = median(deltas)
    residuals = sorted((abs(d - exposure) for d in deltas), reverse=True)
    # Local activity should not disappear into a large stationary background.
    strongest = residuals[: max(1, len(residuals) // 10)]
    # Keep local motion dominant, but do not erase sunrise/sunset and broad
    # weather changes entirely. The clip still needs three changing pairs,
    # so an otherwise static sequence with one flash is not enough.
    return sum(strongest) / len(strongest) + min(8.0, abs(exposure) * 0.25)


def activity_indices(scores, limit=MAX_FRAMES):
    """Keep chronological context and endpoints, favoring changing pairs."""
    if len(scores) <= limit:
        return list(range(len(scores)))
    selected = {round(i * (len(scores) - 1) / 7) for i in range(8)}
    for index in sorted(range(1, len(scores)), key=lambda i: (-scores[i], i)):
        for candidate in (index - 1, index):
            if len(selected) < limit:
                selected.add(candidate)
    return sorted(selected)


def eligible(template: dict, name: str = "") -> bool:
    """Allow camera history, excluding archived, failing and document views."""
    groups = {g.strip().lower() for g in str(template.get("groups") or "").split(",")}
    if "archive" in groups or template.get("capture_failed"):
        return False
    # Local-IP dashboard URLs do not contain the word "hubitat". Identify
    # operational screens from their saved identity as well as their URL.
    name = str(name or template.get("name") or "").lower()
    source = str(template.get("source_template") or "").lower()
    if (
        name.startswith("hubitat")
        or source.startswith("hubitat")
        or groups & {"hubitat", "desktop", "remote-management", "systems", "network"}
    ):
        return False
    url = str(template.get("url") or "").lower()
    if any(host in url for host in ("weather.gov", "noaa.gov/products", "hubitat")):
        return False
    return bool(
        template.get("camera_latitude")
        or template.get("event_buffer_enabled")
        or url.startswith(("rtsp://", "ptzview://"))
        or groups
        & set(VIEWER_CONFIG.get("timelapse_groups", ["marine", "grower", "traffic"]))
    )


def build_timelapse(name: str, now: float | None = None) -> dict | None:
    """Return a finite cached GIF with capture bounds, or no usable history."""
    name = validate_template_name(name)
    template = get_template(name) if name else None
    if not template or not eligible(template, name):
        return None
    now = time.time() if now is None else now
    freshness = source_freshness(
        name, template, datetime.fromtimestamp(now, timezone.utc)
    )
    # Check current source evidence before even reusing a cached clip: a newly
    # captured screenshot must not make an old/retained source appear current.
    if any(
        freshness.get(key)
        for key in (
            "capture_overdue",
            "waiting_for_browser",
            "retained",
            "older",
            "clock_ahead",
            "unchanged_since",
            "low_light",
        )
    ):
        return None
    try:
        cadence = max(60, min(1800, float(template.get("frequency") or 30) * 60))
    except (TypeError, ValueError):
        cadence = 1800
    folder = Path(config.SCREENSHOT_DIRECTORY) / name
    pattern = re.compile(re.escape(name) + r"_(\d{14})\.png$")
    history_hours = 24
    frames = []
    for path in folder.glob(name + "_*.png"):
        match = pattern.fullmatch(path.name)
        if not match or path.is_symlink():
            continue
        try:
            stamp = (
                datetime.strptime(match[1], "%Y%m%d%H%M%S")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
        except ValueError:
            continue
        if now - history_hours * 3600 <= stamp <= now + 5:
            frames.append((stamp, path))
    frames.sort()
    if len(frames) < 6 or now - frames[-1][0] > min(5400, max(1800, cadence * 3)):
        return None
    # Break history at long outages; never animate across a missing afternoon.
    for i in range(len(frames) - 1, 0, -1):
        if frames[i][0] - frames[i - 1][0] > max(1800, cadence * 3):
            frames = frames[i:]
            break
    if len(frames) < 6 or frames[-1][0] - frames[0][0] < 600:
        return None
    if len(frames) > MAX_CANDIDATES:
        frames = [
            frames[round(i * (len(frames) - 1) / (MAX_CANDIDATES - 1))]
            for i in range(MAX_CANDIDATES)
        ]
    root = Path(config.DATABASE_PATH).resolve().parent / "timelapse"
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(name.encode()).hexdigest()
    output, metadata = root / (key + ".gif"), root / (key + ".json")
    identity = hashlib.sha256(
        ("v6-change-history|" + "|".join(p.name for _, p in frames)).encode()
    ).hexdigest()
    # Include source identity so edited feeds cannot reuse another source's clip.
    identity = hashlib.sha256(
        (identity + str(template.get("url"))).encode()
    ).hexdigest()
    with (root / "build.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        try:
            saved = json.loads(metadata.read_text())
            if (
                saved.get("identity") == identity
                and output.exists()
                and now - float(saved.get("end", 0))
                <= min(5400, max(1800, cadence * 3))
            ):
                return {**saved, "path": output}
        except (OSError, ValueError):
            pass
        images, times, scores, previous = [], [], [], None
        for stamp, path in frames:
            clean = path.with_name(path.name + ".clean.png")
            try:
                with Image.open(clean if clean.is_file() else path) as source:
                    source.thumbnail((800, 450))
                    image = source.convert("RGB")
                # Ignore timestamp/caption strips when testing whether the scene changed.
                w, h = image.size
                sample = (
                    image.crop((0, int(h * 0.15), w, int(h * 0.8)))
                    .convert("L")
                    .resize((32, 18))
                )
                scores.append(activity_score(previous, sample))
                previous = sample
                images.append(image)
                times.append(stamp)
            except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
                continue
        if (
            len(images) < 6
            or sum(score >= 1.5 for score in scores) < 3
            or times[-1] - times[0] < 600
        ):
            return None
        if now - times[-1] > min(5400, max(1800, cadence * 3)):
            return None
        if any(b - a > max(1800, cadence * 3) for a, b in zip(times, times[1:])):
            return None
        selected = activity_indices(scores)
        images = [
            ImageOps.fit(images[i], (800, 450)).quantize(
                colors=128, method=Image.Quantize.FASTOCTREE
            )
            for i in selected
        ]
        times = [times[i] for i in selected]
        # Equal playback steps are intentional; gaps are disclosed as sampled history.
        frame_ms = max(
            FRAME_MS, ((20000 + len(images) - 1) // len(images) + 9) // 10 * 10
        )
        record = {
            "identity": identity,
            "start": times[0],
            "end": times[-1],
            "frames": len(images),
            "duration": len(images) * frame_ms / 1000,
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=root, suffix=".gif", delete=False
            ) as handle:
                temporary = Path(handle.name)
            images[0].save(
                temporary,
                format="GIF",
                save_all=True,
                append_images=images[1:],
                duration=frame_ms,
                optimize=False,
            )
            os.replace(temporary, output)
            metadata.write_text(json.dumps(record))
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return {**record, "path": output}
