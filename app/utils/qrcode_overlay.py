"""Minimal utilities for embedding a tiny barcode in screenshots."""

from __future__ import annotations

import hashlib
from typing import List

from PIL import Image, ImageDraw


def generate_micro_barcode(data: str) -> List[bool]:
    """Return a boolean list representing a tiny 1D barcode."""
    bits = "".join(f"{b:08b}" for b in hashlib.sha1(data.encode()).digest())
    return [b == "1" for b in bits[:64]]


def add_micro_barcode(image_path: str, data: str) -> None:
    """Overlay a tiny 1D barcode onto ``image_path`` in the bottom-right corner."""
    pattern = generate_micro_barcode(data)
    scale = 2
    bar_height = 16
    width = len(pattern) * scale
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        x0 = img.width - width - 1
        y0 = img.height - bar_height - 1
        for i, val in enumerate(pattern):
            color = (0, 0, 0) if val else (255, 255, 255)
            draw.rectangle(
                [x0 + i * scale, y0, x0 + (i + 1) * scale - 1, y0 + bar_height],
                fill=color,
            )
        img.save(image_path, "PNG")
