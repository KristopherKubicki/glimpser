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

BRAILLE_RADIUS = 2
BRAILLE_SPACING = 2


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


def _roman_segment_widths(font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
    """Return maximum segment widths for Roman numeral timestamps."""
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    hours = [_to_roman(i) for i in range(24)]
    mins = [_to_roman(i) for i in range(60)]
    seg1 = max(d.textlength(h, font=font) for h in hours)
    seg2 = max(d.textlength(m, font=font) for m in mins)
    seg3 = seg2
    colon_w = d.textlength(":", font=font)
    return seg1, seg2, seg3, colon_w


def _draw_braille_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    radius: int = BRAILLE_RADIUS,
    spacing: int = BRAILLE_SPACING,
    fill: str = "white",
) -> int:
    """Draw ``text`` using simple braille dots and return its width."""

    def _dots(bits: int) -> list[tuple[int, int]]:
        mapping = {
            0: (0, 0),
            1: (0, 1),
            2: (0, 2),
            3: (1, 0),
            4: (1, 1),
            5: (1, 2),
        }
        return [mapping[i] for i in range(6) if bits & (1 << i)]

    x, y = pos
    char_w = 2 * radius + spacing
    for ch in _to_braille(text):
        bits = ord(ch) - 0x2800
        for cx, cy in _dots(bits):
            draw.ellipse(
                (
                    x + cx * char_w - radius,
                    y + cy * (radius * 2 + spacing) - radius,
                    x + cx * char_w + radius,
                    y + cy * (radius * 2 + spacing) + radius,
                ),
                fill=fill,
            )
        x += char_w + spacing
    return x - pos[0]


def _braille_text_width(
    text: str, radius: int = BRAILLE_RADIUS, spacing: int = BRAILLE_SPACING
) -> int:
    """Return the width of ``text`` when drawn with :func:`_draw_braille_text`."""
    char_w = 2 * radius + spacing
    return len(text) * (char_w + spacing) - spacing


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
            font = ImageFont.truetype(name, size)
            if font.getmask("\u2801").getbbox():
                return font
        except OSError:
            continue
    font = ImageFont.load_default()
    if font.getmask("\u2801").getbbox():
        return font
    try:
        path = os.path.join(os.path.dirname(ImageFont.__file__), "DejaVuSansMono.ttf")
        return ImageFont.truetype(path, size)
    except OSError:
        return font


def generate_test_pattern(
    width: int = 1280,
    height: int = 720,
    logo_path: Optional[str] = None,
    camera_name: str | None = None,
    variant: str = "color",
    spinner: str | None = None,
) -> Image.Image:
    """Return a PIL image with calibration aids.
    ``spinner`` overlays a simple spinner glyph on the pattern.
    """

    img = Image.new("RGB", (width, height))

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
    x_start = width - mini_w * (len(mini_709) + len(mini_2020)) - 10 - 100
    y_start = 2 + 10
    for color, label in mini_709 + mini_2020:
        draw.rectangle(
            [x_start, y_start, x_start + mini_w, y_start + mini_h], fill=color
        )
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
    draw.text(
        (width // 2 - tw // 2, bar_h + 6), timestamp, fill="white", font=font_large
    )

    if spinner:
        sb = draw.textbbox((0, 0), spinner, font=font_small)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
        draw.text((width - sw - 10, 10), spinner, fill="white", font=font_small)

    # stable reference patch for tests
    patch_x = width // 2 + 6
    patch_y = height // 2 + 3
    draw.point((patch_x, patch_y), fill=(118, 118, 118))

    # multiple time codes stacked on the right side
    font_right = load_font(26)
    time_simple = timestamp.split(" ")[1]
    formats = [
        time_simple,
        _format_binary_time(time_simple),
        _format_roman_time(time_simple),
        _to_braille(time_simple),
    ]

    segments = [t.replace("\u2812", ":").split(":") for t in formats]
    roman_w1, roman_w2, roman_w3, colon_w = _roman_segment_widths(font_right)
    seg1_max = max(
        draw.textlength("23", font=font_right),
        draw.textlength("10111", font=font_right),
        roman_w1,
        draw.textlength(_to_braille("00"), font=font_right),
    )
    seg2_max = max(
        draw.textlength("59", font=font_right),
        draw.textlength("111011", font=font_right),
        roman_w2,
        draw.textlength(_to_braille("00"), font=font_right),
    )
    seg3_max = seg2_max

    total_w = seg1_max + colon_w + seg2_max + colon_w + seg3_max
    x_start = width - total_w - 10
    y_start = height // 2 - (
        (len(formats) * font_right.size + (len(formats) - 1) * 4) // 2
    )

    for idx, parts in enumerate(segments):
        x = x_start
        y = y_start + idx * (font_right.size + 4)
        if idx == len(formats) - 1:
            _draw_braille_text(
                draw,
                (x + seg1_max - _braille_text_width(parts[0]), y),
                parts[0],
            )
            x += seg1_max
            _draw_braille_text(draw, (x, y), ":")
            x += colon_w
            _draw_braille_text(
                draw,
                (x + seg2_max - _braille_text_width(parts[1]), y),
                parts[1],
            )
            x += seg2_max
            _draw_braille_text(draw, (x, y), ":")
            x += colon_w
            _draw_braille_text(
                draw,
                (x + seg3_max - _braille_text_width(parts[2]), y),
                parts[2],
            )
        else:
            draw.text(
                (x + seg1_max - draw.textlength(parts[0], font=font_right), y),
                parts[0],
                fill="white",
                font=font_right,
            )
            x += seg1_max
            draw.text((x, y), ":", fill="white", font=font_right)
            x += colon_w
            draw.text(
                (x + seg2_max - draw.textlength(parts[1], font=font_right), y),
                parts[1],
                fill="white",
                font=font_right,
            )
            x += seg2_max
            draw.text((x, y), ":", fill="white", font=font_right)
            x += colon_w
            draw.text(
                (x + seg3_max - draw.textlength(parts[2], font=font_right), y),
                parts[2],
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


def save_test_pattern(path: str, **kwargs) -> None:
    """Generate a test pattern image and save it as PNG."""

    img = generate_test_pattern(**kwargs)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, "PNG")
