# app/utils/image_utils.py
"""Helpers for overlaying motion and captions onto images."""

from __future__ import annotations

import datetime
import logging
import os
import textwrap
from contextlib import contextmanager
from typing import Iterator

from PIL import Image, ImageDraw

from app.config import DEBUG
from app.utils.screenshots import load_font

MAX_IMAGE_TIME_DIFF = datetime.timedelta(minutes=5)


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
        logging.error("Error saving image: %s %s", image_path, e)
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
    caption = caption[:64].replace("\n", " ")
    wrapped = textwrap.fill(caption, width=32)
    x = padding
    y = int(image.height - int(font_size * 3) - top_offset)
    bbox = draw.multiline_textbbox((x, y), wrapped, font=font, stroke_width=1)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    background = Image.new(
        "RGBA", (text_w + padding * 2, text_h + padding * 2), (0, 0, 0, 128)
    )
    image.paste(background, (x - padding, y - padding), background)
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )


def save_image(image: Image.Image, image_path: str) -> None:
    """Persist ``image`` to ``image_path`` in PNG format."""

    image.save(image_path, "PNG")
    image.close()


def add_motion_and_caption(
    image_path: str, caption: str | None = None, motion: bool = False
) -> None:
    """Overlay ``caption`` and/or motion indicator onto ``image_path``."""

    if not os.path.exists(image_path):
        return
    if caption is None and not motion:
        return

    with load_image(image_path) as image:
        if image is None:
            return

        try:
            draw = ImageDraw.Draw(image)
            max_height = min(image.height, image.width * 9 // 16)
            font_size = int(max_height * 0.05)
            top_offset = (image.height - max_height) / 2
            font = load_font(font_size)
            if motion:
                _apply_motion_icon(image, draw, font, font_size, top_offset)
            if caption is not None:
                _apply_caption(image, draw, font, font_size, caption, top_offset)
            save_image(image, image_path)
        except Exception as e:  # pragma: no cover - unexpected errors
            logging.error("Error updating image %s : %s", image_path, e)
