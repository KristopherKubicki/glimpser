"""Utilities for generating a broadcast-style test pattern."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Mapping of ASCII digits to their Braille equivalents. Used to display the
# timestamp in Braille on the generated test pattern.
BRAILLE_DIGITS = {
    "0": "\u281a",
    "1": "\u2801",
    "2": "\u2803",
    "3": "\u2809",
    "4": "\u2819",
    "5": "\u2811",
    "6": "\u280b",
    "7": "\u281b",
    "8": "\u2813",
    "9": "\u280a",
    ":": "\u2812",
}


def _to_braille(text: str) -> str:
    """Return the supplied text with digits converted to Braille patterns."""
    return "".join(BRAILLE_DIGITS.get(ch, ch) for ch in text)


FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "LiberationSans-Regular.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Return a TrueType font for overlays."""
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_test_pattern(
    width: int = 1280,
    height: int = 720,
    logo_path: Optional[str] = None,
    camera_name: str | None = None,
) -> Image.Image:
    """Return a PIL image with a colorful test pattern."""

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # background gradient
    start = (20, 0, 40)
    end = (0, 0, 0)
    for y in range(height):
        ratio = y / height
        r = int(start[0] * (1 - ratio) + end[0] * ratio)
        g = int(start[1] * (1 - ratio) + end[1] * ratio)
        b = int(start[2] * (1 - ratio) + end[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # SMPTE-like color bars
    bars = [
        (255, 255, 255),
        (255, 255, 0),
        (0, 255, 255),
        (0, 255, 0),
        (255, 0, 255),
        (255, 0, 0),
        (0, 0, 255),
    ]
    bar_h = height // 6
    bar_w = width // len(bars)
    for i, color in enumerate(bars):
        draw.rectangle([i * bar_w, 0, (i + 1) * bar_w, bar_h], fill=color)

    # checker pattern at the bottom
    sq = 20
    y0 = height - bar_h
    for y in range(y0, height, sq):
        for x in range(0, width, sq):
            fill = (255, 255, 255) if (x // sq + y // sq) % 2 == 0 else (0, 0, 0)
            draw.rectangle([x, y, x + sq - 1, y + sq - 1], fill=fill)

    # time and mystic text
    font_large = load_font(32)
    font_small = load_font(20)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb = draw.textbbox((0, 0), timestamp, font=font_large)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    draw.rectangle(
        [width // 2 - tw // 2 - 4, bar_h + 4, width // 2 + tw // 2 + 4, bar_h + th + 8],
        fill=(0, 0, 0),
    )
    draw.text((width // 2 - tw // 2, bar_h + 6), timestamp, fill="white", font=font_large)

    mystic = "Seek the unseen"
    mb = draw.textbbox((0, 0), mystic, font=font_small)
    mw, mh = mb[2] - mb[0], mb[3] - mb[1]
    draw.text((width // 2 - mw // 2, bar_h + th + 14), mystic, fill="white", font=font_small)

    if camera_name:
        draw.text((10, bar_h + 10), camera_name, fill="white", font=font_small)

    if logo_path and os.path.exists(logo_path):
        with Image.open(logo_path).convert("RGBA") as logo:
            scale = (width * 0.2) / logo.width
            logo = logo.resize((int(logo.width * scale), int(logo.height * scale)))
            img.paste(logo, (width - logo.width - 10, height - logo.height - 10), logo)

    return img


def generate_indian_head_test_pattern(
    width: int = 1280,
    height: int = 720,
    spinner: str | None = None,
) -> Image.Image:
    """Return a grayscale Indian Head-style test pattern with extras."""

    img = Image.new("RGB", (width, height), "gray")
    draw = ImageDraw.Draw(img)

    # Mosaic background inspired by the former geometric pattern
    tri_w = width // 10
    tri_h = height // 10
    colors = [(30, 30, 30), (80, 80, 80)]
    for row in range(10):
        for col in range(20):
            x = col * tri_w // 2
            y = row * tri_h
            color = colors[(row + col) % 2]
            points = [(x, y), (x + tri_w // 2, y + tri_h), (x + tri_w, y)]
            draw.polygon(points, fill=color)

    draw.line((width // 2, 0, width // 2, height), fill="black", width=3)
    draw.line((0, height // 2, width, height // 2), fill="black", width=3)

    for scale in (0.4, 0.6, 0.8):
        radius = int(min(width, height) * scale / 2)
        bbox = (
            width // 2 - radius,
            height // 2 - radius,
            width // 2 + radius,
            height // 2 + radius,
        )
        draw.ellipse(bbox, outline="black", width=3)

    font = load_font(int(height * 0.05))
    text = "PLEASE STAND BY"
    tb = draw.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    draw.text((width // 2 - tw // 2, height // 2 - th // 2), text, fill="black", font=font)

    # Display the current time in multiple languages and Braille near the bottom
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    font_small = load_font(int(height * 0.04))
    lines = [
        f"Time: {timestamp}",
        f"Hora: {timestamp}",
        f"Heure: {timestamp}",
        _to_braille(timestamp),
    ]
    for i, line in enumerate(lines):
        tb = draw.textbbox((0, 0), line, font=font_small)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((width // 2 - tw // 2, height - (len(lines) - i) * (th + 4)), line, fill="white", font=font_small)

    # Optional spinner overlay for fun
    if spinner:
        sb = draw.textbbox((0, 0), spinner, font=font)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
        draw.text((width - sw - 10, 10), spinner, fill="white", font=font)

    return img


def generate_geometric_test_pattern(
    width: int = 1280,
    height: int = 720,
    tiles: int = 10,
    spinner: str | None = None,
) -> Image.Image:
    """Legacy wrapper that now returns the unified test pattern."""

    # `tiles` is ignored but kept for backward compatibility
    return generate_indian_head_test_pattern(width=width, height=height, spinner=spinner)


def save_test_pattern(path: str, **kwargs) -> None:
    """Generate a test pattern image and save it as PNG."""

    img = generate_test_pattern(**kwargs)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, "PNG")
