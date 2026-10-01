# app/utils/image_utils.py
"""Helpers for overlaying motion and captions onto images."""

from __future__ import annotations

import datetime
import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from PIL import Image, ImageDraw

from app.config import DEBUG
from app.utils.screenshots import CAPTURE_PNG_COMPRESSION_LEVEL, load_font

MAX_IMAGE_TIME_DIFF = datetime.timedelta(minutes=5)
CAPTION_OVERLAY_SUPPRESSED_NAMES = {
    "fast.com",
    "weather",
    "comed",
    "eyebatsystemglimpse",
    "phobosworldoverview",
    "phobosworldrelations",
    "phobosworldhistory",
    "abt",
    "abt.com",
    "adblock",
    "axisexperiencerooftop",
    "ais",
    "bingmaps",
    "boatnerdaisgreatlakes",
    "chicagoporttracker",
    "chicagoharbormarinetraffic",
    "cnwpowerhouseeast",
    "cloudping",
    "comedprice",
    "dempsterboatlaunch",
    "energy",
    "earthquakes",
    "faa",
    "fieldmuseum",
    "flightradar",
    "googlemaps",
    "gpsjam",
    "grantpark",
    "lakemichiganmarinetraffic",
    "midway",
    "midwayearthcamlive",
    "midwaylive",
    "milwaukeemarinetraffic",
    "northpointmarina",
    "ohare",
    "piracy",
    "portmilwaukeevesseltracker",
    "skydeck",
    "stream",
    "tarpreservoirlevels",
    "tvguide",
    "uicskyline",
    "wastewater",
    "waze",
    "zoomearth",
}


def find_closest_image(
    directory: str,
    last_caption_time: datetime.datetime,
    max_time_diff: datetime.timedelta = MAX_IMAGE_TIME_DIFF,
) -> str | None:
    """Return the closest motion image not older than ``max_time_diff``."""

    closest_image = None
    min_time_diff = None

    for filename in os.listdir(directory):
        if (
            filename.endswith(".png")
            and "motion" in filename
            and not os.path.islink(os.path.join(directory, filename))
        ):
            timestamp_str = filename.split("_")[0]
            try:
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                time_diff = abs(last_caption_time - timestamp)
                if time_diff > max_time_diff:
                    continue
                if min_time_diff is None or time_diff < min_time_diff:
                    closest_image = filename
                    min_time_diff = time_diff
            except ValueError:
                continue

    return closest_image


@contextmanager
def load_image(image_path: str) -> Iterator[Image.Image]:
    """Yield an RGB image loaded from ``image_path``."""

    try:
        with Image.open(image_path) as img:
            yield img.convert("RGB")
    except Exception as e:  # pragma: no cover - I/O errors depend on env
        if DEBUG:
            os.rename(image_path, image_path.replace(".png", ".broken"))
        else:
            os.unlink(image_path)
        logging.warning("image load issue: %s %s", image_path, e)
        yield None


def _apply_motion_icon(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    font,
    font_size: int,
    top_offset: float,
    padding: int = 6,
) -> None:
    motion_icon = "░"
    text_w = int(draw.textlength(motion_icon, font=font))
    text_h = font_size
    x = int(image.width - text_w - 10)
    y = int(image.height - int(font_size * 3) - top_offset)
    background = Image.new(
        "RGBA", (text_w + padding * 2, text_h + padding * 2), (0, 0, 0, 128)
    )
    image.paste(background, (x - padding, y - padding), background)
    draw.text(
        (x, y),
        motion_icon,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )


def _apply_caption(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    font,
    font_size: int,
    caption: str,
    top_offset: float,
    padding: int = 6,
) -> None:
    # Measure rendered pixels, not character counts: wide letters and font
    # descenders otherwise run past the frame, especially on short captures.
    max_width = max(1, int(image.width * 0.55) - padding * 2)
    remaining = " ".join(caption.split())
    lines = []
    for line_index in range(3):
        if not remaining:
            break
        line = remaining
        while (
            line
            and draw.textbbox((0, 0), line, font=font, stroke_width=1)[2] > max_width
        ):
            line = line[:-1]
        if len(line) < len(remaining):
            if " " in line:
                line = line.rsplit(" ", 1)[0]
            if line_index == 2:
                while (
                    line
                    and draw.textbbox((0, 0), line + "…", font=font, stroke_width=1)[2]
                    > max_width
                ):
                    line = line[:-1]
                line = line.rstrip() + "…"
        lines.append(line)
        remaining = remaining[len(line) :].lstrip()
    wrapped = "\n".join(lines)
    if not wrapped:
        return
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, stroke_width=1)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if text_w > image.width - padding * 4 or text_h > image.height - padding * 4:
        return  # Tiny thumbnails cannot hold a readable caption safely.
    left = padding * 2
    bottom = min(
        image.height - padding * 2, image.height - int(top_offset) - padding * 2
    )
    top = max(padding * 2, bottom - text_h)
    x, y = left - bbox[0], top - bbox[1]
    background = Image.new(
        "RGBA", (text_w + padding * 2, text_h + padding * 2), (0, 0, 0, 128)
    )
    image.paste(background, (left - padding, top - padding), background)
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )


def _caption_overlay_suppressed(image_path: str) -> bool:
    """Return True when a template should keep captures visually clean."""

    camera_name = os.path.basename(os.path.dirname(os.path.realpath(image_path)))
    return caption_overlay_suppressed_name(camera_name)


def caption_overlay_suppressed_name(camera_name: str | None) -> bool:
    """Return True when a camera should prefer clean, caption-free frames."""

    normalized = str(camera_name or "").strip().lower()
    return normalized in CAPTION_OVERLAY_SUPPRESSED_NAMES or normalized.startswith(
        "hubitat"
    )


def save_image(image: Image.Image, image_path: str) -> None:
    """Persist ``image`` to ``image_path`` in PNG format."""
    directory = os.path.dirname(image_path) or "."
    fd, tmp_path = tempfile.mkstemp(
        prefix=".imgtmp_", suffix=".png", dir=directory, text=False
    )
    os.close(fd)
    try:
        image.save(tmp_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)
        os.replace(tmp_path, image_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        image.close()


def add_motion_and_caption(
    image_path: str, caption: str | None = None, motion: bool = False
) -> None:
    """Overlay ``caption`` and/or motion indicator onto ``image_path``."""

    # Many callers pass a "latest" symlink (global or per-camera). We must edit
    # the underlying PNG and leave the symlink intact, otherwise we can replace
    # the symlink with a regular file and/or create partial reads.
    target_path = image_path
    if os.path.islink(image_path):
        target_path = os.path.realpath(image_path)

    if not os.path.exists(target_path):
        return
    if _caption_overlay_suppressed(target_path):
        caption = None
        motion = False
    if caption is None and not motion:
        return

    with load_image(target_path) as image:
        if image is None:
            return

        try:
            draw = ImageDraw.Draw(image)
            max_height = min(image.height, image.width * 9 // 16)
            font_size = max(1, int(max_height * 0.032))
            top_offset = (image.height - max_height) / 2
            font = load_font(font_size)
            if motion:
                _apply_motion_icon(image, draw, font, font_size, top_offset)
            if caption is not None:
                _apply_caption(image, draw, font, font_size, caption, top_offset)
            save_image(image, target_path)
        except Exception as e:  # pragma: no cover - unexpected errors
            logging.error("Error updating image %s : %s", image_path, e)
