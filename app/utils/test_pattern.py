"""Utilities for generating a broadcast-style test pattern."""

from __future__ import annotations

import datetime
import math
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
    """Return a PIL image with an enhanced broadcast-style test pattern."""

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # background gradient with three stops for smoother transitions
    stops = [
        (0, (40, 0, 60)),
        (height // 2, (20, 20, 40)),
        (height, (0, 0, 0)),
    ]
    for y in range(height):
        for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
            if y0 <= y <= y1:
                ratio = (y - y0) / (y1 - y0)
                r = int(c0[0] * (1 - ratio) + c1[0] * ratio)
                g = int(c0[1] * (1 - ratio) + c1[1] * ratio)
                b = int(c0[2] * (1 - ratio) + c1[2] * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b))
                break

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

    # checker pattern limited to the bottom-right quadrant
    sq = 20
    y0 = height - bar_h
    x0 = width * 3 // 4
    for y in range(y0, height, sq):
        for x in range(x0, width, sq):
            fill = (255, 255, 255) if (x // sq + y // sq) % 2 == 0 else (0, 0, 0)
            draw.rectangle([x, y, x + sq - 1, y + sq - 1], fill=fill)

    # grayscale blocks for exposure checking
    block_w = width // 20
    block_h = bar_h // 3
    for i in range(6):
        shade = int(255 * i / 5)
        draw.rectangle(
            [i * block_w + 10, y0 - block_h - 5, (i + 1) * block_w + 10, y0 - 5],
            fill=(shade, shade, shade),
        )

    # fine lines for sharpness tests around center
    center_x = width // 2
    center_y = height // 2
    for offset in range(-20, 25, 5):
        draw.line(
            (center_x + offset, bar_h, center_x + offset, height - bar_h),
            fill="white",
        )
        draw.line(
            (0, center_y + offset, width, center_y + offset),
            fill="white",
        )

    # interlaced lines for moire effect
    for y in range(bar_h, height, 4):
        draw.line((0, y, width, y), fill=(30, 30, 30))

    # wedge calibration dots around the bullseye
    radius = min(width, height) * 0.4
    for angle in range(0, 360, 30):
        a = math.radians(angle)
        x = center_x + radius * math.cos(a)
        y = center_y + radius * math.sin(a)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="white")

    # central bullseye target
    for r in range(60, 0, -20):
        draw.ellipse(
            (
                center_x - r,
                center_y - r,
                center_x + r,
                center_y + r,
            ),
            outline="white",
            width=2,
        )

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

    # timestamp repeated near the vertical center on the right side
    font_right = load_font(24)
    rb = draw.textbbox((0, 0), timestamp, font=font_right)
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    draw.text(
        (width - rw - 10, height // 2 - rh // 2),
        timestamp,
        fill="white",
        font=font_right,
    )

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
        draw.text(
            (width // 2 - tw // 2, height - (len(lines) - i) * (th + 4)),
            line,
            fill="white",
            font=font_small,
        )

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
