"""Utilities for generating a broadcast-style test pattern."""

from __future__ import annotations

import datetime
import math
import os
import time
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

BRAILLE_RADIUS = 3
BRAILLE_SPACING = 3


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


def _format_beats_time(timestamp: str) -> str:
    """Return the time in Swatch Internet Time (".beats")."""
    h, m, s = map(int, timestamp.split(":"))
    total_seconds = h * 3600 + m * 60 + s
    beats = int(((total_seconds + 3600) % 86400) / 86.4)
    return f"@{beats:03d}"


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

    img = Image.new("RGBA", (width, height))
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

    # SMPTE color bars: full intensity row followed by 75 % row
    bars = [
        (255, 255, 255),
        (255, 255, 0),
        (0, 255, 255),
        (0, 255, 0),
        (255, 0, 255),
        (255, 0, 0),
        (0, 0, 255),
    ]
    bar_h = height // 16
    bars_total = bar_h * 2
    bar_w = width // len(bars)
    for i, color in enumerate(bars):
        draw.rectangle([i * bar_w, 0, (i + 1) * bar_w, bar_h], fill=color)
    for i, color in enumerate(bars):
        shade = tuple(int(c * 0.75) for c in color)
        draw.rectangle([i * bar_w, bar_h, (i + 1) * bar_w, bars_total], fill=shade)

    # grayscale staircase under the bars
    step_h = max(4, bar_h // 3)
    num_steps = len(range(0, 256, 12))
    step_w = width // num_steps
    for idx, val in enumerate(range(0, 256, 12)):
        x0 = idx * step_w
        draw.rectangle(
            [x0, bars_total, x0 + step_w, bars_total + step_h],
            fill=(val, val, val),
        )

    # super-white and super-black patches on edges
    patch = 8
    y_patch = bars_total + step_h + 2
    draw.rectangle([0, y_patch, patch, y_patch + patch], fill=(255, 255, 255))
    draw.rectangle([width - patch, y_patch, width, y_patch + patch], fill=(0, 0, 0))

    # subtle synthwave sunrise near the horizon
    sun_r = min(width, height) // 10
    horizon_y = height - bars_total - step_h - sun_r
    sun_cx = width // 4
    shimmer = 1 + 0.05 * math.sin(time.time() * 2)
    for r in range(sun_r, 0, -2):
        ratio = r / sun_r
        color = (
            int(min(255, 255 * ratio * shimmer)),
            int(min(255, (80 + 100 * (1 - ratio)) * shimmer)),
            int(min(255, (150 + 50 * ratio) * shimmer)),
        )
        draw.arc(
            [sun_cx - r, horizon_y - r, sun_cx + r, horizon_y + r],
            start=180,
            end=360,
            fill=color,
            width=2,
        )
    draw.line([(0, horizon_y), (width, horizon_y)], fill=(80, 0, 80))
    for x_off in range(-sun_r, sun_r + 1, sun_r // 4):
        draw.line(
            [
                (sun_cx + x_off, horizon_y),
                (sun_cx + x_off, horizon_y - 5),
            ],
            fill=(80, 0, 80),
        )

    # drifting clouds subtly obscure the sun
    cloud_layer = Image.new("RGBA", (width, height))
    cloud_draw = ImageDraw.Draw(cloud_layer)
    offset = int(time.time() * 10) % (width + sun_r) - sun_r // 2
    base_y = horizon_y - sun_r // 2
    c_rx = sun_r // 2
    c_ry = sun_r // 4
    for i in range(5):
        cx = (offset + i * c_rx * 2) % (width + sun_r) - c_rx
        cy = base_y - (i % 3) * (sun_r // 6)
        cloud_draw.ellipse(
            [cx, cy, cx + c_rx * 2, cy + c_ry],
            fill=(0, 0, 0, 40),
        )
    img = Image.alpha_composite(img, cloud_layer)
    draw = ImageDraw.Draw(img)

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
    x_start = 10
    y_start = 10
    mini_total_w = mini_w * (len(mini_709) + len(mini_2020))
    for color, label in mini_709 + mini_2020:
        draw.rectangle(
            [x_start, y_start, x_start + mini_w, y_start + mini_h], fill=color
        )
        text_color = "white" if sum(color) < 382 else "black"
        draw.text((x_start + 1, y_start + 1), label, fill=text_color, font=font_tiny)
        x_start += mini_w

    # smaller checkerboard aligned with the mini bars
    sq = max(10, mini_w)
    pat_w = mini_total_w
    pat_h = sq * 4
    x0 = 10
    y0 = y_start + mini_h + 5
    for y in range(y0, y0 + pat_h, sq):
        for x in range(x0, x0 + pat_w, sq):
            fill = (
                (255, 255, 255)
                if ((x - x0) // sq + (y - y0) // sq) % 2 == 0
                else (0, 0, 0)
            )
            draw.rectangle([x, y, x + sq - 1, y + sq - 1], fill=fill)

    # grayscale swatch matching checker height
    block_w = mini_w
    block_h = pat_h // 4
    start_x = x0 + pat_w + 5
    for i in range(4):
        shade = int(255 * i / 3)
        draw.rectangle(
            [
                start_x,
                y0 + i * block_h,
                start_x + block_w,
                y0 + (i + 1) * block_h,
            ],
            fill=(shade, shade, shade),
        )

    # fine lines for sharpness tests around center fade outward
    center_x = width // 2
    center_y = height // 2
    max_off = 20
    for offset in range(-max_off, max_off + 1, 5):
        shade = int(255 - (abs(offset) / max_off) * 155)
        alpha = int(200 - (abs(offset) / max_off) * 200)
        color = (shade, shade, shade, alpha)
        draw.line((center_x + offset, 0, center_x + offset, height), fill=color)
        draw.line((0, center_y + offset, width, center_y + offset), fill=color)

    # interlaced lines for moire effect
    for y in range(bars_total + step_h, height, 4):
        draw.line((0, y, width, y), fill=(30, 30, 30))

    # concentric zone-plate in the centre
    zone_radius = min(width, height) // 3
    for r in range(zone_radius, 0, -1):
        shade = int(127.5 * (1 + math.sin(r * r * 0.05)))
        draw.ellipse(
            (
                center_x - r,
                center_y - r,
                center_x + r,
                center_y + r,
            ),
            outline=(shade, shade, shade),
        )

    # wedge calibration dots around the bullseye
    wedge_radius = min(width, height) * 0.4
    for angle in range(0, 360, 30):
        a = math.radians(angle)
        x = center_x + wedge_radius * math.cos(a)
        y = center_y + wedge_radius * math.sin(a)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="white")

    # central bullseye target with fading rings
    for idx, r in enumerate(range(60, 0, -20)):
        shade = 255 - idx * 60
        color = (shade, shade, shade)
        draw.ellipse(
            (
                center_x - r,
                center_y - r,
                center_x + r,
                center_y + r,
            ),
            outline=color,
            width=2,
        )

    # add a simple second hand so the bullseye doubles as a clock face
    h, m, s = map(int, datetime.datetime.now().strftime("%H:%M:%S").split(":"))
    angle = math.radians((s / 60) * 360 - 90)
    hand_len = wedge_radius
    end_x = center_x + hand_len * math.cos(angle)
    end_y = center_y + hand_len * math.sin(angle)
    draw.line((center_x, center_y, end_x, end_y), fill="white", width=2)

    # overlay spinner if provided
    font_small = load_font(20)
    now = datetime.datetime.now()
    timestamp = now.strftime("%H:%M:%S")
    date_text = now.strftime("%Y-%m-%d")

    if spinner:
        sw = _braille_text_width(spinner)
        _draw_braille_text(draw, (width - sw - 30, 20), spinner)

    # stable reference patch for tests
    patch_x = width // 2 + 6
    patch_y = height // 2 + 3
    draw.point((patch_x, patch_y), fill=(118, 118, 118))

    # multiple time codes stacked on the right side
    font_right = load_font(26)
    font_binary = load_font(22)
    font_braille = load_font(30)
    time_simple = timestamp
    beats_time = _format_beats_time(time_simple)
    formats = [
        time_simple,
        _format_binary_time(time_simple),
        _format_roman_time(time_simple),
        _to_braille(time_simple),
        beats_time,
    ]

    fonts = [font_right, font_binary, font_right, font_braille, font_right]
    segments = [t.replace("\u2812", ":").split(":") for t in formats]

    braille_idx = 3

    roman_w1, roman_w2, roman_w3, colon_w_std = _roman_segment_widths(font_right)
    colon_w = max(
        colon_w_std, draw.textlength(":", font=font_binary), _braille_text_width(":")
    )
    colon_gap = colon_w + 2
    seg1_max = max(
        draw.textlength("23", font=font_right),
        draw.textlength("10111", font=font_binary),
        roman_w1,
        _braille_text_width("00"),
    )
    seg2_max = max(
        draw.textlength("59", font=font_right),
        draw.textlength("111011", font=font_binary),
        roman_w2,
        _braille_text_width("00"),
    )
    seg3_max = seg2_max

    beats_w = draw.textlength(beats_time, font=font_right)
    total_w = max(seg1_max + colon_gap + seg2_max + colon_gap + seg3_max, beats_w)
    x_start = width - total_w - 30

    line_heights = [
        font_right.size,
        font_binary.size,
        font_right.size,
        font_braille.size,
        font_right.size,
    ]
    spacing_y = 22
    extra_gap = 30
    total_h = sum(line_heights) + spacing_y * (len(line_heights) - 1) + extra_gap
    y_start = height // 2 - total_h // 2 + 20

    # lighten the stacked clocks so they distract less from the pattern
    clock_color = (160, 160, 160)
    draw.text((30, y_start), date_text, fill=clock_color, font=font_right)
    current_y = y_start
    for idx, parts in enumerate(segments):
        x = x_start
        y = current_y
        font = fonts[idx]
        if idx == braille_idx:
            x -= _braille_text_width("0")
            _draw_braille_text(
                draw,
                (x + seg1_max - _braille_text_width(parts[0]), y),
                parts[0],
                fill=clock_color,
            )
            x += seg1_max
            _draw_braille_text(draw, (x, y), ":", fill=clock_color)
            x += colon_gap
            _draw_braille_text(
                draw,
                (x + seg2_max - _braille_text_width(parts[1]), y),
                parts[1],
                fill=clock_color,
            )
            x += seg2_max
            _draw_braille_text(draw, (x, y), ":", fill=clock_color)
            x += colon_gap
            _draw_braille_text(
                draw,
                (x + seg3_max - _braille_text_width(parts[2]), y),
                parts[2],
                fill=clock_color,
            )
            current_y += line_heights[idx] + spacing_y
            if idx == 1:
                current_y += extra_gap
        elif len(parts) == 1:
            draw.text(
                (x + total_w - draw.textlength(parts[0], font=font), y),
                parts[0],
                fill=clock_color,
                font=font,
            )
            current_y += line_heights[idx] + spacing_y
            if idx == 1:
                current_y += extra_gap
        else:
            draw.text(
                (x + seg1_max - draw.textlength(parts[0], font=font), y),
                parts[0],
                fill=clock_color,
                font=font,
            )
            x += seg1_max
            draw.text((x, y), ":", fill=clock_color, font=font)
            x += colon_gap
            draw.text(
                (x + seg2_max - draw.textlength(parts[1], font=font), y),
                parts[1],
                fill=clock_color,
                font=font,
            )
            x += seg2_max
            draw.text((x, y), ":", fill=clock_color, font=font)
            x += colon_gap
            draw.text(
                (x + seg3_max - draw.textlength(parts[2], font=font), y),
                parts[2],
                fill=clock_color,
                font=font,
            )
            current_y += line_heights[idx] + spacing_y
            if idx == 1:
                current_y += extra_gap
    if camera_name:
        draw.text(
            (10, bars_total + step_h + 10), camera_name, fill="white", font=font_small
        )

    if logo_path and os.path.exists(logo_path):
        with Image.open(logo_path).convert("RGBA") as logo:
            scale = (width * 0.2) / logo.width
            logo = logo.resize((int(logo.width * scale), int(logo.height * scale)))
            img.paste(logo, (width - logo.width - 10, height - logo.height - 10), logo)

    return img.convert("RGB")


def save_test_pattern(path: str, **kwargs) -> None:
    """Generate a test pattern image and save it as PNG."""

    img = generate_test_pattern(**kwargs)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, "PNG")
