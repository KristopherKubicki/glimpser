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


def _to_roman(num: int) -> str:
    """Return the number as a Roman numeral ("N" for zero)."""
    if num == 0:
        return "N"
    numerals = [
        ("M", 1000),
        ("CM", 900),
        ("D", 500),
        ("CD", 400),
        ("C", 100),
        ("XC", 90),
        ("L", 50),
        ("XL", 40),
        ("X", 10),
        ("IX", 9),
        ("V", 5),
        ("IV", 4),
        ("I", 1),
    ]
    result = []
    for symbol, value in numerals:
        count, num = divmod(num, value)
        result.append(symbol * count)
    return "".join(result)


def _format_roman_time(timestamp: str) -> str:
    """Return the timestamp represented with Roman numerals."""
    h, m, s = map(int, timestamp.split(":"))
    return f"{_to_roman(h)}:{_to_roman(m)}:{_to_roman(s)}"


def _format_binary_time(timestamp: str) -> str:
    """Return the timestamp in binary notation."""
    h, m, s = map(int, timestamp.split(":"))
    return f"{h:05b}:{m:06b}:{s:06b}"


FONT_CANDIDATES = [
    "DejaVuSansMono.ttf",
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
    """Return a PIL image with a broadcast-style test pattern and calibration aids."""

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

    # miniature SMPTE bars and wide-gamut Rec.2020 bars
    mini_709 = [
        ((191, 191, 191), "W"),
        ((191, 191, 0), "Y"),
        ((0, 191, 191), "C"),
        ((0, 191, 0), "G"),
        ((191, 0, 191), "M"),
        ((191, 0, 0), "R"),
        ((0, 0, 191), "B"),
        ((0, 0, 0), "K"),
    ]
    mini_2020 = [
        ((255, 0, 0), "R"),
        ((0, 255, 0), "G"),
        ((0, 0, 255), "B"),
        ((0, 255, 255), "C"),
        ((255, 0, 255), "M"),
        ((255, 255, 0), "Y"),
    ]
    mini_w = max(2, width // 100)
    mini_h = bar_h // 4
    font_tiny = load_font(8)
    x_start = width - mini_w * (len(mini_709) + len(mini_2020)) - 10 - 50
    y_start = 2 + 10
    for color, label in mini_709 + mini_2020:
        draw.rectangle([x_start, y_start, x_start + mini_w, y_start + mini_h], fill=color)
        text_color = "white" if sum(color) < 382 else "black"
        draw.text((x_start + 1, y_start + 1), label, fill=text_color, font=font_tiny)
        x_start += mini_w

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

    # stable reference patch for tests
    patch_x = width // 2 + 6
    patch_y = height // 2 + 3
    draw.point((patch_x, patch_y), fill=(118, 118, 118))

    # timestamp repeated near the vertical center on the right side
    font_right = load_font(24)
    rb = draw.textbbox((0, 0), timestamp, font=font_right)
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    x_pos = max(width - rw - 10, width // 2 + 10)
    draw.text(
        (x_pos, height // 2 - rh // 2),
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

    for row in range(5):
        for col in range(10):
            x = col * tri_w // 2
            y = row * tri_h
            color = colors[(row + col) % 2]
            points = [(x, y), (x + tri_w // 2, y + tri_h), (x + tri_w, y)]
            draw.polygon(points, fill=color)

    # miniature SMPTE bars and wide-gamut Rec.2020 bars in the upper right
    mini_709 = [
        ((191, 191, 191), "W"),
        ((191, 191, 0), "Y"),
        ((0, 191, 191), "C"),
        ((0, 191, 0), "G"),
        ((191, 0, 191), "M"),
        ((191, 0, 0), "R"),
        ((0, 0, 191), "B"),
        ((0, 0, 0), "K"),
    ]
    mini_2020 = [
        ((255, 0, 0), "R"),
        ((0, 255, 0), "G"),
        ((0, 0, 255), "B"),
        ((0, 255, 255), "C"),
        ((255, 0, 255), "M"),
        ((255, 255, 0), "Y"),
    ]
    bar_h = height // 6
    mini_w = max(2, width // 100)
    mini_h = bar_h // 4
    font_tiny = load_font(8)
    x_start = width - mini_w * (len(mini_709) + len(mini_2020)) - 10 - 50
    y_start = 2 + 10
    for color, label in mini_709 + mini_2020:
        draw.rectangle([x_start, y_start, x_start + mini_w, y_start + mini_h], fill=color)
        text_color = "white" if sum(color) < 382 else "black"
        draw.text((x_start + 1, y_start + 1), label, fill=text_color, font=font_tiny)
        x_start += mini_w

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

    # Display the current time in several numeral systems near the right center
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    font_small = load_font(int(height * 0.04))
    h, m, s = timestamp.split(":")
    lines = [
        f"{h}:{m}:{s}",
        f"{_to_braille(h)}:{_to_braille(m)}:{_to_braille(s)}",
        f"{_to_roman(int(h))}:{_to_roman(int(m))}:{_to_roman(int(s))}",
        f"{int(h):05b}:{int(m):06b}:{int(s):06b}",
    ]

    hours = [h, _to_braille(h), _to_roman(int(h)), f"{int(h):05b}"]
    mins = [m, _to_braille(m), _to_roman(int(m)), f"{int(m):06b}"]
    secs = [s, _to_braille(s), _to_roman(int(s)), f"{int(s):06b}"]
    parts = list(zip(hours, mins, secs))

    colon_w = draw.textlength(":", font=font_small)
    hours_w = [draw.textlength(text, font=font_small) for text in hours]
    mins_w = [draw.textlength(text, font=font_small) for text in mins]
    secs_w = [draw.textlength(text, font=font_small) for text in secs]
    max_min_w = max(mins_w)
    max_sec_w = max(secs_w)
    colon_x2 = width - 10 - max_sec_w
    colon_x1 = colon_x2 - colon_w - max_min_w

    metrics = [draw.textbbox((0, 0), line, font=font_small) for line in lines]
    heights = [m[3] - m[1] for m in metrics]
    spacing = 8
    total_height = sum(heights) + spacing * (len(lines) - 1)
    y = height // 2 - total_height // 2
    for (h_part, m_part, s_part), hgt, hw in zip(parts, heights, hours_w):
        line = f"{h_part}:{m_part}:{s_part}"
        x = colon_x1 - hw
        draw.text((x, y), line, fill="white", font=font_small)
        y += hgt + spacing

    # Optional spinner overlay for fun
    if spinner:
        sb = draw.textbbox((0, 0), spinner, font=font)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
        draw.text((width - sw - 10, 10), spinner, fill="white", font=font)

    # Extra calibration graphics
    cx, cy = width // 2, height // 2
    draw.line((cx, 0, cx, height), fill="white")
    draw.line((0, cy, width, cy), fill="white")
    for frac in (0.45, 0.30, 0.15):
        r = int(height * frac / 2)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline="white")

    grad_y = height - 50
    step_w = width // 44
    for i in range(11):
        shade = round(i * 255 / 10)
        draw.rectangle(
            (10 + i * step_w, grad_y, 10 + (i + 1) * step_w - 1, grad_y + 20),
            fill=(shade, shade, shade),
        )

    ramp_w = step_w * 51
    ramp_y = grad_y - 30
    for i in range(ramp_w):
        shade = round(i * 255 / (ramp_w - 1))
        draw.line((10 + i, ramp_y, 10 + i, ramp_y + 10), fill=(shade, shade, shade))
    patch_w = ramp_w // 51
    for i in range(51):
        shade = round(i * 255 / 50)
        bg = (240, 240, 240) if shade < 128 else (15, 15, 15)
        left = 10 + i * patch_w
        draw.rectangle((left, ramp_y + 12, left + patch_w - 1, ramp_y + 22), fill=bg)
        inner_left = left + 2
        inner_right = left + patch_w - 3
        if inner_right >= inner_left:
            draw.rectangle(
                (inner_left, ramp_y + 14, inner_right, ramp_y + 20),
                fill=(shade, shade, shade),
            )

    cb_x = width - 22
    cb_y = height - 22
    for yy in range(cb_y, cb_y + 20):
        for xx in range(cb_x, cb_x + 20):
            color = (255, 255, 255) if (xx + yy) % 2 == 0 else (0, 0, 0)
            draw.point((xx, yy), fill=color)

    wedge_x = 10
    wedge_y = bar_h + 10
    for freq in range(1, 11):
        for x in range(20):
            col = 255 if (x // freq) % 2 == 0 else 0
            draw.line((wedge_x + x, wedge_y, wedge_x + x, wedge_y + 20), fill=(col, col, col))
        wedge_x += 22
    wedge_x = 10
    wedge_y += 24
    for freq in range(1, 11):
        for y in range(20):
            col = 255 if (y // freq) % 2 == 0 else 0
            draw.line((wedge_x, wedge_y + y, wedge_x + 20, wedge_y + y), fill=(col, col, col))
        wedge_x += 22

    target_y = ramp_y - 40
    intensities = [125, 200, 255]
    for i, val in enumerate(intensities):
        left = 10 + i * 24
        draw.rectangle((left, target_y, left + 20, target_y + 20), fill=(val, val, val))

    draw.rectangle((width - 70, 10, width - 20, 40), fill=(118, 118, 118))
    draw.rectangle((width - 70, 50, width - 20, 80), fill=(215, 170, 150))

    grid_color = (13, 13, 13)
    for x in range(0, width, 100):
        draw.line((x, 0, x, height - 1), fill=grid_color)
    for y in range(0, height, 100):
        draw.line((0, y, width - 1, y), fill=grid_color)

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
