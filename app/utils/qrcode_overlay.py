"""Minimal utilities for embedding a tiny QR-style code in screenshots."""

from __future__ import annotations

import hashlib
from typing import List

from PIL import Image, ImageDraw


def generate_micro_qr(data: str) -> List[List[bool]]:
    """Return an 8x8 boolean matrix representing a tiny QR-like code."""
    bits = "".join(f"{b:08b}" for b in hashlib.sha1(data.encode()).digest())
    matrix = [[False] * 8 for _ in range(8)]

    # 2x2 orientation squares in three corners
    for i in range(2):
        for j in range(2):
            matrix[i][j] = True
            matrix[i][6 + j] = True
            matrix[6 + i][j] = True

    idx = 0
    for y in range(2, 8):
        for x in range(2, 8):
            if x >= 6 and y >= 6:
                continue
            matrix[y][x] = bits[idx] == "1"
            idx = (idx + 1) % len(bits)
    return matrix


def add_micro_qr(image_path: str, data: str) -> None:
    """Overlay a tiny QR-like code onto ``image_path`` in the bottom-right corner."""
    matrix = generate_micro_qr(data)
    scale = 2
    qr_size = len(matrix) * scale
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        x0 = img.width - qr_size - 1
        y0 = img.height - qr_size - 1
        for y, row in enumerate(matrix):
            for x, val in enumerate(row):
                color = (0, 0, 0) if val else (255, 255, 255)
                draw.rectangle(
                    [
                        x0 + x * scale,
                        y0 + y * scale,
                        x0 + (x + 1) * scale - 1,
                        y0 + (y + 1) * scale - 1,
                    ],
                    fill=color,
                )
        img.save(image_path, "PNG")
