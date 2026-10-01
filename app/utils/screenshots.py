"""Capture, annotate and process screenshots from various sources.

The module provides high level helpers to download or grab images using
Chrome, yt-dlp or ffmpeg, apply overlays and store them in structured
directories.  It manages caching of HTTP status codes and integrates with
user activity checks so interactive sessions are not disrupted.
"""

import base64
import datetime
import email.utils
import errno
import fcntl
import hashlib
import io
import ipaddress
import json
import logging
import math
import os
import platform
import random
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from fractions import Fraction
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse

import numpy as np
import psutil
import requests
import urllib3
import yt_dlp as youtube_dl
from dateutil import tz
from pdf2image import convert_from_bytes
from PIL import Image, ImageDraw, ImageFile, ImageFilter, ImageFont, ImageOps
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from werkzeug.utils import secure_filename

from app import capture_policy, config
from app.config import (
    ANALYZE_DURATION_DEFAULT,
    ANALYZE_DURATION_OTHER,
    ANALYZE_DURATION_RTSP,
    CAPTURE_TIMEOUT,
    DEBUG,
    FFMPEG_HWACCEL,
    FFMPEG_PATH,
    FFPROBE_PATH,
    NUM_FRAMES,
    PROBE_SIZE_DEFAULT,
    PROBE_SIZE_OTHER,
    PROBE_SIZE_RTSP,
    SCREENSHOT_DIRECTORY,
    TZ,
    UA,
)
from app.utils import status_cache, user_activity
from app.utils.eufy_cloud import EufyCloudError, resolve_eufy_to_snapshot
from app.utils.google_sdm import (
    GoogleSdmError,
    build_webrtc_preview_url,
    resolve_sdm_to_rtsp,
    stable_key_for_resolved_rtsp,
    stable_sdm_key_for_url,
)
from app.utils.logging_utils import sanitize_url
from app.utils.validators import url_matches_host, validate_proxy, validate_url

from .chrome_utils import (
    browser_supports_gl,
    get_chrome_path,
    get_chrome_version,
    is_chrome_debug_port_open,
)
from .network import is_system_online, network_state

os.environ["WDM_LOG"] = "0"
os.environ["WDM_LOG_LEVEL"] = "0"
logging.getLogger("webdriver_manager").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.ERROR)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# PIL may raise 'image file is truncated' if a screenshot is incomplete.
# Allow truncated images to load so we can still overlay timestamps and
# handle files gracefully.
ImageFile.LOAD_TRUNCATED_IMAGES = True
_PIL_RESAMPLING = getattr(Image, "Resampling", Image)

_ORPHAN_BROWSER_CLEANUP_LAST = 0.0
_ORPHAN_BROWSER_CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("ORPHAN_BROWSER_CLEANUP_INTERVAL_SECONDS", "600")
)
_ORPHAN_BROWSER_MAX_AGE_SECONDS = int(
    os.getenv("ORPHAN_BROWSER_MAX_AGE_SECONDS", "1800")
)
_STABILIZE_ALLOWED_MODES = {"", "off", "previous", "rolling_5m", "rolling_30m"}
_STABILIZE_MAX_SHIFT_PX = {
    "previous": 24,
    "rolling_5m": 36,
    "rolling_30m": 48,
}
_STABILIZE_MIN_OVERLAP_RATIO = 0.72
_STABILIZE_REFERENCE_LIMIT = 5
_STABILIZE_REFERENCE_WINDOWS = {
    "previous": None,
    "rolling_5m": 300,
    "rolling_30m": 1800,
}
_STABILIZE_SAMPLE_MAX_DIM = 192
_STABILIZE_SCORE_MIN = 0.68
_NIGHT_ENHANCE_ALLOWED_MODES = {"", "off", "light", "medium", "strong"}
_NIGHT_ENHANCE_MIN_SCORE = 0.68
_NIGHT_ENHANCE_MAX_SHIFT_PX = 12
_NIGHT_ENHANCE_TRIGGER_MEAN = 104.0
_NIGHT_ENHANCE_TRIGGER_BRIGHT_RATIO = 0.12
_NIGHT_ENHANCE_GAMMA = {"light": 0.82, "medium": 0.72, "strong": 0.62}
_NIGHT_ENHANCE_BLEND = {"light": 0.35, "medium": 0.52, "strong": 0.68}
_NIGHT_ENHANCE_FLOOR_LIFT = {"light": 6.0, "medium": 12.0, "strong": 18.0}
_NIGHT_ENHANCE_AUTOCONTRAST = {"light": 0.2, "medium": 0.6, "strong": 1.0}
_NIGHT_ENHANCE_UNSHARP = {
    "light": (0.8, 80, 3),
    "medium": (1.1, 110, 3),
    "strong": (1.4, 135, 4),
}
_HORIZON_LEVEL_ALLOWED_MODES = {"", "off", "roll", "smooth"}
# Default to the upper lake/sky band; buoy cameras often place the true horizon
# higher than fixed pier/harbor cameras, especially when the frame is rolling.
_HORIZON_LEVEL_DEFAULT_ROI = "0.04,0.12,0.92,0.36"
# Buoy feeds can roll well past a few degrees in rough conditions. Keep this
# bounded enough to avoid chasing arbitrary scene edges on non-horizon shots.
_HORIZON_LEVEL_MAX_DEGREES = 14.0
_HORIZON_LEVEL_STEP_DEGREES = 0.25
_HORIZON_LEVEL_MIN_CONFIDENCE = 2.75
_HORIZON_LEVEL_MIN_APPLY_DEGREES = 0.25
_HORIZON_LEVEL_SMOOTH_ALPHA = 0.5
_HORIZON_LEVEL_SMOOTH_RESET_DEGREES = 3.0
_BURST_ENHANCE_ALLOWED_MODES = {"", "off", "full_frame", "roi"}
_BURST_ENHANCE_ALLOWED_PROFILES = {"", "clean", "hybrid", "crisp"}
_BURST_ENHANCE_REFERENCE_LIMIT = 4
_BURST_ENHANCE_REFERENCE_WINDOW_SECONDS = 1800
_BURST_ENHANCE_MAX_SHIFT_PX = 12
_BURST_ENHANCE_MIN_SCORE = 0.68
_BURST_ENHANCE_FULL_FRAME_MAX_DIM = 1280
_BURST_ENHANCE_LOWDEF_UPSCALE_MAX_DIM = 960
_BURST_ENHANCE_MIN_DIM = 48
_BURST_ENHANCE_TIMESTAMP_WIDTH_RATIO = 0.32
_BURST_ENHANCE_TIMESTAMP_HEIGHT_RATIO = 0.18
_BURST_ENHANCE_TIMESTAMP_MIN_WIDTH = 96
_BURST_ENHANCE_TIMESTAMP_MIN_HEIGHT = 28
_VISUAL_TIMESTAMP_ALLOWED_MODES = {"clean", "compact", "debug", "off", "full"}
_STATIC_CHART_DARK_MODE_NAMES = {
    "aps",
    "bandwidthrx",
    "bandwidthtx",
    "bartol",
    "bartolwind",
    "drought",
    "icecover",
    "mccookhydrograph",
    "meteorshower",
    "noaa",
    "swpcspaceweatheroverview",
}
_STATIC_CHART_DARK_MODE_URL_MARKERS = (
    "droughtmonitor.unl.edu/data/png/current/current_midwest_trd.png",
    "services.swpc.noaa.gov/images/swx-overview-large.gif",
    "water.noaa.gov/resources/hydrographs/mcci2_hg.png",
    "www.glerl.noaa.gov/data/ice/spaghetti/mic_ice_compare.png",
    "www.weather.gov/wwamap/png/lot.png",
    "www3.aps.anl.gov/asd/operations/gifplots/hdsrcomfort.png",
)

_safe_import_pynput = user_activity._safe_import_pynput
_send_input_event = user_activity._send_input_event
idle_seconds_loginctl = user_activity.idle_seconds_loginctl
idle_seconds_macos = user_activity.idle_seconds_macos
idle_seconds_windows = user_activity.idle_seconds_windows
idle_seconds_x11 = user_activity.idle_seconds_x11
keyboard = user_activity.keyboard
mouse = user_activity.mouse
on_click = user_activity.on_click
on_move = user_activity.on_move
on_press = user_activity.on_press
on_scroll = user_activity.on_scroll
user_active = user_activity.user_active


def _normalize_stabilize_mode(mode: str | None) -> str:
    """Return a supported stabilization mode or ``off``."""

    normalized = str(mode or "").strip().lower()
    if normalized not in _STABILIZE_ALLOWED_MODES:
        return "off"
    if normalized in {"", "off"}:
        return "off"
    return normalized


def _normalize_horizon_level_mode(mode: str | None) -> str:
    """Return a supported horizon-leveling mode or ``off``."""

    normalized = str(mode or "").strip().lower()
    if normalized not in _HORIZON_LEVEL_ALLOWED_MODES:
        return "off"
    if normalized in {"", "off"}:
        return "off"
    return normalized


def _normalize_burst_enhance_mode(mode: str | None) -> str:
    """Return a supported still-image burst enhancement mode or ``off``."""

    normalized = str(mode or "").strip().lower()
    if normalized not in _BURST_ENHANCE_ALLOWED_MODES:
        return "off"
    if normalized in {"", "off"}:
        return "off"
    return normalized


def _normalize_burst_enhance_profile(profile: str | None) -> str:
    """Return a supported burst-fusion profile."""

    normalized = str(profile or "").strip().lower()
    if normalized not in _BURST_ENHANCE_ALLOWED_PROFILES:
        return "clean"
    return normalized or "clean"


def _normalize_stream_burst_frames(
    value: object | None,
    *,
    default: int = NUM_FRAMES,
    is_hdhomerun_stream: bool = False,
) -> int:
    """Return a bounded live-stream burst size."""

    try:
        frames = int(value or 0)
    except (TypeError, ValueError):
        frames = 0
    if frames <= 0:
        frames = int(default or NUM_FRAMES or 1)
    frames = max(1, min(frames, 32))
    if is_hdhomerun_stream:
        frames = max(1, min(frames, 2))
    return frames


def _normalize_stream_burst_span_ms(value: object | None) -> int:
    """Return a bounded live-stream burst window in milliseconds."""

    try:
        span_ms = int(value or 0)
    except (TypeError, ValueError):
        span_ms = 0
    return max(0, min(span_ms, 10000))


def _effective_stream_burst_settings(
    url: str | None,
    template: dict | None,
    *,
    is_hdhomerun_stream: bool = False,
) -> tuple[int | None, int | None]:
    """Return effective per-capture burst settings for a live stream."""

    template = template or {}
    configured_frames = _normalize_stream_burst_frames(
        template.get("stream_burst_frames"),
        default=NUM_FRAMES,
        is_hdhomerun_stream=is_hdhomerun_stream,
    )
    configured_span_ms = _normalize_stream_burst_span_ms(
        template.get("stream_burst_span_ms")
    )
    explicit_frames = int(template.get("stream_burst_frames") or 0) > 0
    explicit_span = int(template.get("stream_burst_span_ms") or 0) > 0
    if explicit_frames or explicit_span:
        return configured_frames, configured_span_ms

    parsed = urlparse(str(url or ""))
    is_rtsp_like = parsed.scheme.lower() in {"rtsp", "rtsps"}
    is_lan_stream = _is_lan_target(parsed.hostname)
    event_buffer_enabled = _template_flag_enabled(template.get("event_buffer_enabled"))
    if (
        is_rtsp_like
        and is_lan_stream
        and event_buffer_enabled
        and not is_hdhomerun_stream
    ):
        boosted_frames = max(configured_frames, min(max(NUM_FRAMES * 2, 5), 9))
        cached_fingerprint = _get_stream_fingerprint(str(url or ""))
        fps_value = None
        if cached_fingerprint:
            try:
                fps_value = float(Fraction(str(cached_fingerprint.get("fps") or "0")))
            except (TypeError, ValueError, ZeroDivisionError):
                fps_value = None
        if fps_value is not None and fps_value <= 1.5:
            # Very low-fps RTSP cameras can need most of the template timeout
            # just to deliver the first keyframe. Keep some burst context, but
            # do not auto-boost them into a burst that cannot finish in time.
            return min(boosted_frames, 2), 1200
        return boosted_frames, 1200
    return configured_frames, configured_span_ms


def _apply_low_fps_rtsp_burst_cap(
    url: str | None, frames: int, span_ms: int
) -> tuple[int, int]:
    """Clamp oversized RTSP bursts when cached stream fps is very low."""

    cached_fingerprint = _get_stream_fingerprint(str(url or ""))
    if not cached_fingerprint:
        return frames, span_ms

    try:
        fps_value = float(Fraction(str(cached_fingerprint.get("fps") or "0")))
    except (TypeError, ValueError, ZeroDivisionError):
        return frames, span_ms

    if 0 < fps_value <= 1.5 and frames > 2:
        return 2, span_ms
    return frames, span_ms


def _normalize_night_enhance_mode(mode: str | None) -> str:
    """Return a supported night still-enhancement mode or ``off``."""

    normalized = str(mode or "").strip().lower()
    if normalized not in _NIGHT_ENHANCE_ALLOWED_MODES:
        return "off"
    if normalized in {"", "off"}:
        return "off"
    return normalized


def _normalize_visual_timestamp_mode(mode: str | None = None) -> str:
    """Return the still-frame timestamp overlay mode.

    ``clean`` keeps capture pixels free of Glimpser labels while preserving
    filename/database timestamps for the UI. ``compact`` burns one local
    timestamp. ``debug`` keeps the older diagnostic local/UTC overlay.
    """

    normalized = str(mode or config.VISUAL_TIMESTAMP_MODE or "clean").strip().lower()
    if normalized not in _VISUAL_TIMESTAMP_ALLOWED_MODES:
        return "clean"
    if normalized in {"", "off"}:
        return "clean"
    if normalized == "full":
        return "debug"
    return normalized


def _stream_frame_quality_score(image: Image.Image) -> float:
    """Return a lightweight sharpness/detail score for a decoded stream frame."""

    grayscale = np.asarray(image.convert("L"), dtype=np.float32)
    if grayscale.size == 0:
        return 0.0
    contrast = float(np.std(grayscale))
    edge_x = (
        float(np.mean(np.abs(np.diff(grayscale, axis=1))))
        if grayscale.shape[1] > 1
        else 0.0
    )
    edge_y = (
        float(np.mean(np.abs(np.diff(grayscale, axis=0))))
        if grayscale.shape[0] > 1
        else 0.0
    )
    return contrast * 0.35 + edge_x + edge_y


def _has_repeated_stream_rows(image: Image.Image) -> bool:
    """Detect decoder smears that repeat a textured row down a large frame region."""
    if image.height < 128 or image.width < 64:
        return False
    # Preserve vertical resolution and tolerate sub-pixel decoder noise.
    sample = image.convert("L").resize((min(image.width, 256), image.height))
    pixels = np.asarray(sample, dtype=np.float32)
    # Adjacent rows in high-resolution night images naturally differ by less
    # than one luma level. Compare to the run's anchor so gradual real scene
    # changes accumulate instead of being mistaken for decoder repetition.
    anchor = pixels[0]
    longest = run = 0
    for row in pixels[1:]:
        if row.std() > 12 and np.abs(row - anchor).mean() < 1.5:
            run += 1
        else:
            anchor = row
            run = 0
        longest = max(longest, run)
    return longest >= max(64, int(image.height * 0.15))


def _has_vertical_stream_smear(image: Image.Image) -> bool:
    """Catch long decoder bands that preserve columns but erase scene detail."""
    if image.height < 512 or image.width < 512:
        return False
    pixels = np.asarray(
        image.convert("L").resize((min(image.width, 256), image.height)),
        dtype=np.float32,
    )
    vertical_change = np.abs(np.diff(pixels, axis=0)).mean(axis=1)
    horizontal_change = np.abs(np.diff(pixels, axis=1)).mean(axis=1)
    window = min(256, max(128, image.height // 8))
    rolling = np.convolve(
        vertical_change, np.ones(window, dtype=np.float32) / window, mode="valid"
    )
    start = int(np.argmin(rolling))
    return (
        float(rolling[start]) < 1.0
        and float(horizontal_change[start : start + window].mean()) > 8.0
    )


def _select_best_stream_frame(
    tmpdirname: str, name: str
) -> tuple[str | None, str | None]:
    """Choose the best valid stream frame from a burst directory."""

    candidates: list[tuple[float, str]] = []
    fallback_path: str | None = None
    fallback_reason: str | None = None
    frame_names = sorted(os.listdir(tmpdirname))

    for index, frame_name in enumerate(frame_names):
        frame_path = os.path.join(tmpdirname, frame_name)
        if not os.path.isfile(frame_path):
            continue
        try:
            file_size = os.path.getsize(frame_path)
            with Image.open(frame_path) as image:
                reject_reason = _captured_frame_rejection_reason(image)
                if reject_reason is None and _has_repeated_stream_rows(image):
                    reject_reason = "decode_smear"
                if (
                    reject_reason is None
                    and name
                    in capture_policy.CAPTURE_POLICY.get("slow_rtsp_cameras", [])
                    and _has_vertical_stream_smear(image)
                ):
                    reject_reason = "vertical_decode_smear"
                if reject_reason is not None:
                    if fallback_path is None:
                        fallback_path = frame_path
                        fallback_reason = reject_reason
                    continue
                score = _stream_frame_quality_score(image)
            score += min(file_size / 4096.0, 256.0) * 0.04
            score += index * 0.1
            candidates.append((score, frame_path))
        except Exception as exc:
            logging.debug(
                "[%s] Skipping stream burst frame %s: %s", name, frame_path, exc
            )

    if candidates:
        candidates.sort(key=lambda row: row[0])
        return candidates[-1][1], None
    return fallback_path, fallback_reason


def _static_chart_dark_mode_enabled(
    name: str,
    template_settings: dict | None,
    dark: bool,
    source_url: str | None = None,
) -> bool:
    """Return whether a direct still chart should receive pixel dark mode."""

    if not dark:
        return False

    normalized_name = str(name or "").strip().lower()
    if normalized_name in _STATIC_CHART_DARK_MODE_NAMES:
        return True

    raw_url = str(source_url or (template_settings or {}).get("url") or "")
    parsed = urlparse(raw_url)
    url_key = f"{parsed.netloc}{parsed.path}".strip().lower()
    return any(marker in url_key for marker in _STATIC_CHART_DARK_MODE_URL_MARKERS)


def _darken_static_chart_image(image: Image.Image, name: str) -> Image.Image:
    """Darken neutral chart ink/paper while preserving colored data and legends."""

    rgb = image.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    luma = (
        arr[..., 0].astype(np.float32) * 0.299
        + arr[..., 1].astype(np.float32) * 0.587
        + arr[..., 2].astype(np.float32) * 0.114
    )
    mean_luma = float(luma.mean())
    light_ratio = float((luma >= 210.0).mean())
    if mean_luma < 128.0 or light_ratio < 0.35:
        logging.debug(
            "[%s] Static chart dark mode skipped; mean=%.1f light_ratio=%.3f",
            name,
            mean_luma,
            light_ratio,
        )
        return rgb

    logging.info(
        "[%s] Applied static chart dark mode; mean=%.1f light_ratio=%.3f",
        name,
        mean_luma,
        light_ratio,
    )
    # Colored lines and warning regions encode data. Inverting them changes that
    # meaning, so transform only near-neutral paper, labels, and grid lines.
    neutral = arr.max(axis=2).astype(np.int16) - arr.min(axis=2) <= 20
    rendered = arr.copy()
    rendered[neutral] = 255 - rendered[neutral]
    return Image.fromarray(rendered)


def _sample_grayscale(image: Image.Image) -> tuple[np.ndarray, float, float]:
    """Return a small grayscale sample plus scale factors back to full size."""

    gray = image.convert("L")
    width, height = gray.size
    max_dimension = max(width, height)
    if max_dimension <= _STABILIZE_SAMPLE_MAX_DIM:
        sample = np.asarray(gray, dtype=np.float32)
        return sample, 1.0, 1.0

    scale = max_dimension / _STABILIZE_SAMPLE_MAX_DIM
    sample_width = max(32, int(round(width / scale)))
    sample_height = max(32, int(round(height / scale)))
    sample = np.asarray(
        gray.resize((sample_width, sample_height), _PIL_RESAMPLING.BILINEAR),
        dtype=np.float32,
    )
    return sample, width / sample_width, height / sample_height


def _collect_stabilization_reference_paths(final_path: str, mode: str) -> list[str]:
    """Return recent screenshot paths that can anchor stabilization."""

    mode = _normalize_stabilize_mode(mode)
    if mode == "off":
        return []

    camera_dir = os.path.dirname(final_path)
    if not camera_dir or not os.path.isdir(camera_dir):
        return []

    now = time.time()
    window_seconds = _STABILIZE_REFERENCE_WINDOWS.get(mode)
    candidates: list[tuple[float, str]] = []
    for filename in os.listdir(camera_dir):
        if not filename.endswith(".png") or filename.endswith(".orig.png"):
            continue
        path = os.path.join(camera_dir, filename)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        try:
            modified = os.path.getmtime(path)
        except OSError:
            continue
        if window_seconds is not None and now - modified > window_seconds:
            continue
        candidates.append((modified, path))

    candidates.sort(reverse=True)
    limit = 1 if mode == "previous" else _STABILIZE_REFERENCE_LIMIT
    return [path for _, path in candidates[:limit]]


def _collect_burst_reference_paths(final_path: str) -> list[str]:
    """Return a short recent frame history for still-image burst fusion."""

    camera_dir = os.path.dirname(final_path)
    if not camera_dir or not os.path.isdir(camera_dir):
        return []

    now = time.time()
    candidates: list[tuple[float, str]] = []
    for filename in os.listdir(camera_dir):
        if not filename.endswith(".png") or filename.endswith(".orig.png"):
            continue
        path = os.path.join(camera_dir, filename)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        try:
            modified = os.path.getmtime(path)
        except OSError:
            continue
        if now - modified > _BURST_ENHANCE_REFERENCE_WINDOW_SECONDS:
            continue
        candidates.append((modified, path))

    candidates.sort(reverse=True)
    return [path for _, path in candidates[:_BURST_ENHANCE_REFERENCE_LIMIT]]


def _build_reference_sample(
    reference_paths: list[str], sample_size: tuple[int, int]
) -> np.ndarray | None:
    """Average recent reference frames into one grayscale sample."""

    sample_width, sample_height = sample_size
    accumulated = None
    count = 0

    for path in reference_paths:
        try:
            with Image.open(path) as image:
                sample = np.asarray(
                    image.convert("L").resize(
                        (sample_width, sample_height),
                        _PIL_RESAMPLING.BILINEAR,
                    ),
                    dtype=np.float32,
                )
        except Exception as exc:
            logging.debug("Skipping stabilize reference %s: %s", path, exc)
            continue

        if accumulated is None:
            accumulated = sample
        else:
            accumulated += sample
        count += 1

    if accumulated is None or count == 0:
        return None
    return accumulated / float(count)


def _estimate_translation(
    current_sample: np.ndarray,
    reference_sample: np.ndarray,
    max_shift: int,
) -> tuple[int, int, float]:
    """Estimate the translation needed to align ``current_sample``."""

    height, width = current_sample.shape
    min_width = max(12, int(width * _STABILIZE_MIN_OVERLAP_RATIO))
    min_height = max(12, int(height * _STABILIZE_MIN_OVERLAP_RATIO))
    best_dx = 0
    best_dy = 0
    best_score = -1.0

    for dy in range(-max_shift, max_shift + 1):
        overlap_height = height - abs(dy)
        if overlap_height < min_height:
            continue
        current_y = max(0, dy)
        reference_y = max(0, -dy)

        for dx in range(-max_shift, max_shift + 1):
            overlap_width = width - abs(dx)
            if overlap_width < min_width:
                continue
            current_x = max(0, dx)
            reference_x = max(0, -dx)

            current_crop = current_sample[
                current_y : current_y + overlap_height,
                current_x : current_x + overlap_width,
            ]
            reference_crop = reference_sample[
                reference_y : reference_y + overlap_height,
                reference_x : reference_x + overlap_width,
            ]

            current_centered = current_crop - current_crop.mean()
            reference_centered = reference_crop - reference_crop.mean()
            denominator = np.linalg.norm(current_centered) * np.linalg.norm(
                reference_centered
            )
            if denominator <= 1e-6:
                continue

            score = float(
                np.multiply(current_centered, reference_centered).sum() / denominator
            )
            if score > best_score:
                best_dx = dx
                best_dy = dy
                best_score = score

    return best_dx, best_dy, best_score


def _apply_translation_crop(
    image: Image.Image, shift_x: int, shift_y: int
) -> Image.Image:
    """Apply a translational stabilization crop and resize back to full size."""

    width, height = image.size
    crop_left = max(0, -shift_x)
    crop_top = max(0, -shift_y)
    crop_right = max(0, shift_x)
    crop_bottom = max(0, shift_y)

    if crop_left + crop_right >= width // 4 or crop_top + crop_bottom >= height // 4:
        return image

    crop_box = (crop_left, crop_top, width - crop_right, height - crop_bottom)
    if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
        return image

    cropped = image.crop(crop_box)
    return cropped.resize((width, height), _PIL_RESAMPLING.LANCZOS)


def _fit_box_to_bounds(
    center_x: float,
    center_y: float,
    box_width: float,
    box_height: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    """Return a clamped pixel box centered on ``center_x``/``center_y``."""

    box_width = min(float(image_width), max(float(_BURST_ENHANCE_MIN_DIM), box_width))
    box_height = min(
        float(image_height), max(float(_BURST_ENHANCE_MIN_DIM), box_height)
    )
    left = int(round(center_x - box_width / 2.0))
    top = int(round(center_y - box_height / 2.0))
    right = left + int(round(box_width))
    bottom = top + int(round(box_height))

    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > image_width:
        left -= right - image_width
        right = image_width
    if bottom > image_height:
        top -= bottom - image_height
        bottom = image_height
    left = max(0, left)
    top = max(0, top)
    right = min(image_width, right)
    bottom = min(image_height, bottom)
    return left, top, right, bottom


def _parse_burst_enhance_roi(
    roi_value: str | None, image_size: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """Parse one ROI box and expand it to the source aspect ratio."""

    text = str(roi_value or "").strip()
    if not text:
        return None

    image_width, image_height = image_size
    for segment in text.split(";"):
        parts = [part.strip() for part in segment.split(",") if part.strip()]
        if len(parts) < 4:
            continue
        try:
            values = [float(part) for part in parts[:4]]
        except ValueError:
            continue

        if max(values) <= 1.0:
            left = values[0] * image_width
            top = values[1] * image_height
            box_width = values[2] * image_width
            box_height = values[3] * image_height
        else:
            left, top, box_width, box_height = values

        if box_width < _BURST_ENHANCE_MIN_DIM or box_height < _BURST_ENHANCE_MIN_DIM:
            continue

        center_x = left + box_width / 2.0
        center_y = top + box_height / 2.0
        target_aspect = image_width / max(1.0, float(image_height))
        box_aspect = box_width / max(1.0, float(box_height))
        if box_aspect > target_aspect:
            box_height = box_width / target_aspect
        else:
            box_width = box_height * target_aspect
        return _fit_box_to_bounds(
            center_x,
            center_y,
            box_width,
            box_height,
            image_width,
            image_height,
        )
    return None


def _parse_capture_crop_roi(
    roi_value: str | None, image_size: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """Parse one capture crop ROI without changing its aspect ratio."""

    text = str(roi_value or "").strip()
    if not text:
        return None

    image_width, image_height = image_size
    for segment in text.split(";"):
        parts = [part.strip() for part in segment.split(",") if part.strip()]
        if len(parts) < 4:
            continue
        try:
            values = [float(part) for part in parts[:4]]
        except ValueError:
            continue

        if max(values) <= 1.0:
            left = values[0] * image_width
            top = values[1] * image_height
            box_width = values[2] * image_width
            box_height = values[3] * image_height
        else:
            left, top, box_width, box_height = values

        if box_width < _BURST_ENHANCE_MIN_DIM or box_height < _BURST_ENHANCE_MIN_DIM:
            continue

        return _fit_box_to_bounds(
            left + box_width / 2.0,
            top + box_height / 2.0,
            box_width,
            box_height,
            image_width,
            image_height,
        )
    return None


def _crop_captured_image(
    image: Image.Image, roi_value: str | None, name: str
) -> Image.Image:
    """Apply a raw capture-side crop before overlays or derived enhancements."""

    crop_box = _parse_capture_crop_roi(roi_value, image.size)
    if crop_box is None:
        return image
    cropped = image.crop(crop_box)
    logging.info(
        "[%s] Applied capture crop roi=%s output=%sx%s",
        name,
        roi_value,
        cropped.size[0],
        cropped.size[1],
    )
    return cropped


def _normalize_capture_rotation(degrees: object) -> int:
    """Return a supported capture rotation in clockwise degrees."""

    try:
        value = int(degrees or 0)
    except (TypeError, ValueError):
        return 0
    if value == 270:
        return -90
    if value == -270:
        return 90
    if value == -180:
        return 180
    return value if value in {-90, 0, 90, 180} else 0


def _rotate_captured_image(
    image: Image.Image, degrees: object, name: str
) -> Image.Image:
    """Rotate a captured still before lens correction and enhancement."""

    rotation = _normalize_capture_rotation(degrees)
    if rotation == 0:
        return image
    if rotation == -90:
        rotated = image.transpose(Image.Transpose.ROTATE_90)
    elif rotation == 90:
        rotated = image.transpose(Image.Transpose.ROTATE_270)
    else:
        rotated = image.transpose(Image.Transpose.ROTATE_180)
    logging.info(
        "[%s] Applied capture rotation degrees=%s output=%sx%s",
        name,
        rotation,
        rotated.size[0],
        rotated.size[1],
    )
    return rotated


def _parse_lens_correction_spec(spec: str | None) -> dict[str, float | str] | None:
    """Parse a capture-side lens correction spec.

    Supported form:
    ``rectilinear:fov=115,src_fov=180,zoom=0.9``.
    """

    raw = str(spec or "").strip().lower()
    if raw in {"", "off", "none"}:
        return None

    mode = raw
    params_text = ""
    if ":" in raw:
        mode, params_text = raw.split(":", 1)
    if mode in {"fisheye", "fisheye_rectilinear"}:
        mode = "rectilinear"
    if mode != "rectilinear":
        return None

    params: dict[str, float | str] = {
        "mode": "rectilinear",
        "fov": 115.0,
        "src_fov": 180.0,
        "zoom": 1.0,
    }
    for part in re.split(r"[,;]\s*", params_text):
        if not part or "=" not in part:
            continue
        key, value = [item.strip() for item in part.split("=", 1)]
        if key not in {"fov", "src_fov", "zoom"}:
            continue
        try:
            params[key] = float(value)
        except ValueError:
            continue

    params["fov"] = min(max(float(params["fov"]), 60.0), 170.0)
    params["src_fov"] = min(max(float(params["src_fov"]), 90.0), 220.0)
    params["zoom"] = min(max(float(params["zoom"]), 0.5), 2.0)
    return params


def _remap_rgb_array(
    source: np.ndarray, source_x: np.ndarray, source_y: np.ndarray
) -> Image.Image:
    """Bilinearly remap an RGB array using floating source coordinates."""

    height, width = source.shape[:2]
    valid = (
        (source_x >= 0)
        & (source_x <= width - 1)
        & (source_y >= 0)
        & (source_y <= height - 1)
    )
    x0 = np.floor(source_x).astype(np.int32)
    y0 = np.floor(source_y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    x0 = np.clip(x0, 0, width - 1)
    y0 = np.clip(y0, 0, height - 1)
    weight_x = (source_x - x0)[..., None]
    weight_y = (source_y - y0)[..., None]
    top = source[y0, x0] * (1 - weight_x) + source[y0, x1] * weight_x
    bottom = source[y1, x0] * (1 - weight_x) + source[y1, x1] * weight_x
    output = top * (1 - weight_y) + bottom * weight_y
    output[~valid] = 0
    return Image.fromarray(np.clip(output, 0, 255).astype(np.uint8))


def _rectilinear_lens_correction(
    image: Image.Image,
    *,
    fov: float,
    src_fov: float,
    zoom: float,
) -> Image.Image:
    """Project an equidistant fisheye frame into a rectilinear view."""

    source = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width = source.shape[:2]
    grid_y, grid_x = np.indices((height, width), dtype=np.float32)
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    focal = (width / 2.0) / math.tan(math.radians(fov) / 2.0) * zoom
    norm_x = (grid_x - center_x) / focal
    norm_y = (grid_y - center_y) / focal
    radius = np.sqrt(norm_x * norm_x + norm_y * norm_y)
    theta = np.arctan(radius)
    phi = np.arctan2(norm_y, norm_x)
    fisheye_radius = min(width, height) * 0.49
    source_radius = theta / (math.radians(src_fov) / 2.0) * fisheye_radius
    source_x = center_x + source_radius * np.cos(phi)
    source_y = center_y + source_radius * np.sin(phi)
    return _remap_rgb_array(source, source_x, source_y)


def _correct_lens_captured_image(
    image: Image.Image, spec: str | None, name: str
) -> Image.Image:
    """Apply configured capture-side lens correction."""

    parsed = _parse_lens_correction_spec(spec)
    if not parsed:
        return image
    if parsed.get("mode") == "rectilinear":
        corrected = _rectilinear_lens_correction(
            image,
            fov=float(parsed["fov"]),
            src_fov=float(parsed["src_fov"]),
            zoom=float(parsed["zoom"]),
        )
        logging.info(
            "[%s] Applied lens correction spec=%s output=%sx%s",
            name,
            spec,
            corrected.size[0],
            corrected.size[1],
        )
        return corrected
    return image


def _parse_horizon_level_roi(
    roi_value: str | None, image_size: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """Return the horizon-detection ROI for an image."""

    return _parse_capture_crop_roi(roi_value or _HORIZON_LEVEL_DEFAULT_ROI, image_size)


def _estimate_horizon_level_angle(
    image: Image.Image,
    roi_value: str | None = None,
    *,
    max_degrees: float = _HORIZON_LEVEL_MAX_DEGREES,
) -> tuple[float, float] | None:
    """Estimate the rotation angle that makes the strongest horizon edge flat."""

    width, height = image.size
    if width < 80 or height < 60:
        return None

    scale = min(1.0, 480.0 / float(width))
    work_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    gray = (
        image.convert("L")
        .resize(work_size, resample=_PIL_RESAMPLING.BICUBIC)
        .filter(ImageFilter.GaussianBlur(radius=1.0))
    )
    roi_box = _parse_horizon_level_roi(roi_value, gray.size)
    if roi_box is None:
        return None

    angles = np.arange(
        -max_degrees,
        max_degrees + (_HORIZON_LEVEL_STEP_DEGREES / 2.0),
        _HORIZON_LEVEL_STEP_DEGREES,
    )
    best: tuple[float, float] | None = None
    for angle in angles:
        rotated = gray.rotate(
            float(angle),
            resample=_PIL_RESAMPLING.BICUBIC,
            expand=False,
            fillcolor=128,
        )
        roi = np.asarray(rotated.crop(roi_box), dtype=np.float32)
        if roi.shape[0] < 12 or roi.shape[1] < 24:
            continue
        row_energy = np.abs(np.diff(roi, axis=0)).mean(axis=1)
        if row_energy.size < 5:
            continue
        peak_idx = int(row_energy.argmax())
        if peak_idx <= 1 or peak_idx >= row_energy.size - 2:
            continue
        score = float(row_energy[peak_idx] / (np.median(row_energy) + 1e-6))
        if best is None or score > best[1]:
            best = (float(angle), score)

    if best is None or best[1] < _HORIZON_LEVEL_MIN_CONFIDENCE:
        return None
    return best


def _horizon_level_fill_color(image: Image.Image) -> tuple[int, int, int]:
    """Use edge colors for rotation fill so temporary corners are not black."""

    source = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if source.size == 0:
        return (0, 0, 0)
    edge = np.concatenate(
        [
            source[0, :, :],
            source[-1, :, :],
            source[:, 0, :],
            source[:, -1, :],
        ],
        axis=0,
    )
    return tuple(int(v) for v in np.median(edge, axis=0))


def _crop_leveled_horizon(image: Image.Image, angle: float) -> Image.Image:
    """Crop away rotation corners and restore the original frame size."""

    width, height = image.size
    radians = abs(math.radians(angle))
    margin_x = int(math.sin(radians) * height / 2.0) + 2
    margin_y = int(math.sin(radians) * width / 2.0) + 2
    margin_x = min(max(margin_x, 0), width // 4)
    margin_y = min(max(margin_y, 0), height // 4)
    if margin_x <= 0 and margin_y <= 0:
        return image
    if width - (margin_x * 2) < 16 or height - (margin_y * 2) < 16:
        return image
    cropped = image.crop((margin_x, margin_y, width - margin_x, height - margin_y))
    return cropped.resize((width, height), resample=_PIL_RESAMPLING.LANCZOS)


def _smooth_horizon_level_angle(angle: float, final_path: str, name: str) -> float:
    """Dampen horizon correction changes across captures for timelapses."""

    state_path = Path(final_path).parent / "horizon_level_state.json"
    previous = None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        previous = float(data.get("angle"))
    except Exception:
        previous = None

    smoothed = angle
    if previous is not None and abs(previous) <= _HORIZON_LEVEL_MAX_DEGREES:
        if abs(angle - previous) <= _HORIZON_LEVEL_SMOOTH_RESET_DEGREES:
            smoothed = previous * (1.0 - _HORIZON_LEVEL_SMOOTH_ALPHA) + angle * (
                _HORIZON_LEVEL_SMOOTH_ALPHA
            )

    try:
        state_path.write_text(
            json.dumps({"angle": smoothed, "updated": time.time(), "name": name}),
            encoding="utf-8",
        )
    except OSError as exc:
        logging.debug("[%s] Horizon level state write failed: %s", name, exc)

    return smoothed


def _level_horizon_captured_image(
    image: Image.Image,
    mode: str | None,
    roi_value: str | None,
    final_path: str,
    name: str,
) -> Image.Image:
    """Rotate buoy/lake frames so the detected horizon stays level."""

    normalized_mode = _normalize_horizon_level_mode(mode)
    if normalized_mode == "off":
        return image

    estimate = _estimate_horizon_level_angle(image, roi_value)
    if estimate is None:
        logging.debug("[%s] Horizon level skipped: no confident horizon", name)
        return image

    angle, confidence = estimate
    if normalized_mode == "smooth":
        angle = _smooth_horizon_level_angle(angle, final_path, name)
    if abs(angle) < _HORIZON_LEVEL_MIN_APPLY_DEGREES:
        return image

    rotated = image.rotate(
        angle,
        resample=_PIL_RESAMPLING.BICUBIC,
        expand=False,
        fillcolor=_horizon_level_fill_color(image),
    )
    leveled = _crop_leveled_horizon(rotated, angle)
    logging.info(
        "[%s] Applied horizon level mode=%s angle=%.2f confidence=%.2f output=%sx%s",
        name,
        normalized_mode,
        angle,
        confidence,
        leveled.size[0],
        leveled.size[1],
    )
    return leveled


def _has_existing_screenshot(name: str) -> bool:
    """Return true when a template already has at least one valid stored PNG."""

    camera_dir = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(str(name)))
    if not os.path.isdir(camera_dir):
        return False
    prefix = f"{secure_filename(str(name))}_"
    for entry in os.listdir(camera_dir):
        if entry == "latest_camera.png":
            continue
        if not entry.startswith(prefix) or not entry.endswith(".png"):
            continue
        path = os.path.join(camera_dir, entry)
        if not os.path.isfile(path) or not _is_valid_png(path):
            continue
        try:
            with Image.open(path) as existing:
                if _captured_frame_rejection_reason(existing) is None:
                    return True
        except Exception:
            continue
    return False


def _crop_for_burst_enhance(
    image: Image.Image,
    mode: str,
    roi_box: tuple[int, int, int, int] | None,
) -> Image.Image:
    """Return the working image for burst enhancement."""

    if mode == "roi" and roi_box is not None:
        return image.crop(roi_box)
    return image


def _normalize_composite_view_mode(mode: str | None) -> str:
    """Return the normalized composite layout mode."""

    normalized = str(mode or "").strip().lower()
    if normalized in {"grid", "hero_strip"}:
        return normalized
    return "off"


def _parse_composite_view_spec(
    spec_value: str | None, image_size: tuple[int, int]
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Parse labeled composite ROI entries from ``Label@x,y,w,h`` segments."""

    text = str(spec_value or "").strip()
    if not text:
        return []

    image_width, image_height = image_size
    panels: list[tuple[str, tuple[int, int, int, int]]] = []
    for index, segment in enumerate(text.split(";"), start=1):
        segment = segment.strip()
        if not segment:
            continue
        if "@" in segment:
            label, coords_text = segment.split("@", 1)
        else:
            label, coords_text = f"Panel {index}", segment
        label = str(label or f"Panel {index}").strip()[:32]
        parts = [part.strip() for part in coords_text.split(",") if part.strip()]
        if len(parts) < 4:
            continue
        try:
            values = [float(part) for part in parts[:4]]
        except ValueError:
            continue

        if max(values) <= 1.0:
            left = values[0] * image_width
            top = values[1] * image_height
            box_width = values[2] * image_width
            box_height = values[3] * image_height
        else:
            left, top, box_width, box_height = values

        if box_width < _BURST_ENHANCE_MIN_DIM or box_height < _BURST_ENHANCE_MIN_DIM:
            continue

        center_x = left + box_width / 2.0
        center_y = top + box_height / 2.0
        box = _fit_box_to_bounds(
            center_x,
            center_y,
            box_width,
            box_height,
            image_width,
            image_height,
        )
        panels.append((label or f"Panel {index}", box))
        if len(panels) >= 4:
            break
    return panels


def _composite_layout_boxes(
    mode: str, image_size: tuple[int, int], panel_count: int
) -> list[tuple[int, int, int, int]]:
    """Return output panel rectangles for the requested composite layout."""

    width, height = image_size
    gap = max(8, min(width, height) // 64)
    label_height = max(28, min(42, height // 18))

    if panel_count <= 0:
        return []

    if mode == "hero_strip" and panel_count > 1:
        strip_count = panel_count - 1
        strip_height = max(label_height + 80, int(round(height * 0.28)))
        hero_height = max(label_height + 120, height - strip_height - (gap * 3))
        boxes = [(gap, gap, width - gap, gap + hero_height)]
        strip_width = (width - (gap * (strip_count + 1))) // max(strip_count, 1)
        strip_top = gap * 2 + hero_height
        for idx in range(strip_count):
            left = gap + idx * (strip_width + gap)
            right = left + strip_width
            boxes.append((left, strip_top, right, height - gap))
        return boxes[:panel_count]

    columns = 1 if panel_count == 1 else 2
    rows = int(np.ceil(panel_count / columns))
    cell_width = (width - gap * (columns + 1)) // columns
    cell_height = (height - gap * (rows + 1)) // rows
    boxes: list[tuple[int, int, int, int]] = []
    for idx in range(panel_count):
        row = idx // columns
        col = idx % columns
        left = gap + col * (cell_width + gap)
        top = gap + row * (cell_height + gap)
        boxes.append((left, top, left + cell_width, top + cell_height))
    return boxes


def _render_composite_view(
    image: Image.Image,
    mode: str | None,
    spec_value: str | None,
    name: str,
) -> Image.Image:
    """Render a split-screen composite from multiple labeled ROIs."""

    normalized_mode = _normalize_composite_view_mode(mode)
    if normalized_mode == "off":
        return image

    panels = _parse_composite_view_spec(spec_value, image.size)
    if not panels:
        logging.info("[%s] Composite view skipped; no valid panels", name)
        return image

    canvas = Image.new("RGB", image.size, (10, 10, 10))
    draw = ImageDraw.Draw(canvas)
    output_boxes = _composite_layout_boxes(normalized_mode, image.size, len(panels))
    label_height = max(28, min(42, image.size[1] // 18))

    for (label, crop_box), output_box in zip(panels, output_boxes):
        left, top, right, bottom = output_box
        panel_width = max(1, right - left)
        panel_height = max(1, bottom - top)
        crop = image.crop(crop_box)
        content_height = max(1, panel_height - label_height)
        fitted = ImageOps.fit(
            crop,
            (panel_width, content_height),
            method=_PIL_RESAMPLING.LANCZOS,
        )
        canvas.paste(fitted, (left, top + label_height))
        draw.rectangle((left, top, right, top + label_height), fill=(18, 18, 18))
        draw.text((left + 10, top + 6), label, fill=(245, 245, 245))
        draw.rectangle((left, top, right, bottom), outline=(45, 45, 45), width=2)

    logging.info(
        "[%s] Rendered composite view mode=%s panels=%d",
        name,
        normalized_mode,
        len(panels),
    )
    return canvas


def _timestamp_overlay_box(image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Return a conservative bottom-right box that covers the timestamp overlay."""

    width, height = image_size
    box_width = min(
        width,
        max(
            _BURST_ENHANCE_TIMESTAMP_MIN_WIDTH,
            int(round(width * _BURST_ENHANCE_TIMESTAMP_WIDTH_RATIO)),
        ),
    )
    box_height = min(
        height,
        max(
            _BURST_ENHANCE_TIMESTAMP_MIN_HEIGHT,
            int(round(height * _BURST_ENHANCE_TIMESTAMP_HEIGHT_RATIO)),
        ),
    )
    return width - box_width, height - box_height, width, height


def _neutralize_reference_overlay(
    reference_image: Image.Image, current_image: Image.Image
) -> Image.Image:
    """Replace the likely timestamp region in a reference frame with current pixels."""

    if reference_image.size != current_image.size:
        return reference_image

    overlay_box = _timestamp_overlay_box(reference_image.size)
    neutralized = reference_image.copy()
    neutralized.paste(current_image.crop(overlay_box), overlay_box)
    return neutralized


def _estimate_reference_shift(
    reference_image: Image.Image,
    current_image: Image.Image,
) -> tuple[int, int, float]:
    """Estimate the crop-resize shift needed to align a reference frame."""

    reference_sample, scale_x, scale_y = _sample_grayscale(reference_image)
    current_sample, _, _ = _sample_grayscale(current_image)
    sample_shift = max(
        1,
        int(round(_BURST_ENHANCE_MAX_SHIFT_PX / max(scale_x, scale_y, 1.0))),
    )
    shift_dx, shift_dy, score = _estimate_translation(
        reference_sample,
        current_sample,
        sample_shift,
    )
    shift_x = int(round(-shift_dx * scale_x))
    shift_y = int(round(-shift_dy * scale_y))
    return shift_x, shift_y, score


def _blur3_rgb(image_arr: np.ndarray) -> np.ndarray:
    """Return a lightweight RGB box blur used for detail transfer."""

    padded = np.pad(image_arr, ((1, 1), (1, 1), (0, 0)), mode="edge")
    return (
        padded[:-2, :-2]
        + padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + padded[1:-1, :-2]
        + padded[1:-1, 1:-1]
        + padded[1:-1, 2:]
        + padded[2:, :-2]
        + padded[2:, 1:-1]
        + padded[2:, 2:]
    ) / 9.0


def _grayscale_laplacian_score(image_arr: np.ndarray) -> float:
    """Return a simple sharpness score for one RGB frame."""

    gray = (
        image_arr[..., 0] * 0.299
        + image_arr[..., 1] * 0.587
        + image_arr[..., 2] * 0.114
    )
    laplacian = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(np.mean(np.abs(laplacian)))


def _fuse_burst_frames(
    frame_arrays: list[np.ndarray], profile: str
) -> tuple[np.ndarray, str]:
    """Fuse aligned burst frames into one still image."""

    if not frame_arrays:
        raise ValueError("burst fusion requires at least one frame")
    if len(frame_arrays) == 1:
        return frame_arrays[0], "single"

    profile = _normalize_burst_enhance_profile(profile)
    sharpness_scores = [
        (_grayscale_laplacian_score(frame_arr), idx)
        for idx, frame_arr in enumerate(frame_arrays)
    ]
    sharpness_scores.sort(reverse=True)
    median_arr = np.median(np.stack(frame_arrays, axis=0), axis=0)

    if profile == "clean":
        return np.clip(median_arr, 0, 255), "median"

    if profile == "crisp":
        lucky_count = min(4, len(frame_arrays))
        lucky = np.mean(
            [frame_arrays[idx] for _, idx in sharpness_scores[:lucky_count]], axis=0
        )
        return np.clip(lucky, 0, 255), "lucky"

    sharpest = frame_arrays[sharpness_scores[0][1]]
    detail = sharpest - _blur3_rgb(sharpest)
    hybrid = median_arr + 0.35 * detail
    return np.clip(hybrid, 0, 255), "hybrid"


def _enhance_captured_image(
    image: Image.Image,
    final_path: str,
    name: str,
    mode: str | None,
    profile: str | None,
    roi_value: str | None,
) -> Image.Image:
    """Apply still-image burst fusion to full frames or one ROI crop.

    ``full_frame`` is meant for low-resolution scenic and infrastructure
    cameras, while ``roi`` is intended for duplicate templates that turn a
    stable subsection into a dedicated zoomed view.
    """

    mode = _normalize_burst_enhance_mode(mode)
    if mode == "off":
        return image

    if mode == "full_frame" and max(image.size) > _BURST_ENHANCE_FULL_FRAME_MAX_DIM:
        logging.info(
            "[%s] Burst enhance skipped; frame too large for full-frame mode (%sx%s)",
            name,
            image.size[0],
            image.size[1],
        )
        return image

    roi_box = _parse_burst_enhance_roi(roi_value, image.size) if mode == "roi" else None
    if mode == "roi" and roi_box is None:
        logging.info("[%s] Burst enhance skipped; ROI mode needs a valid roi box", name)
        return image

    working_current = _crop_for_burst_enhance(image, mode, roi_box)
    frames: list[np.ndarray] = [np.asarray(working_current, dtype=np.float32)]
    accepted_references = 0

    for path in _collect_burst_reference_paths(final_path):
        try:
            with Image.open(path) as reference_image:
                reference_image = reference_image.convert("RGB")
                reference_work = _crop_for_burst_enhance(reference_image, mode, roi_box)
                if reference_work.size != working_current.size:
                    reference_work = reference_work.resize(
                        working_current.size, _PIL_RESAMPLING.LANCZOS
                    )
                reference_work = _neutralize_reference_overlay(
                    reference_work,
                    working_current,
                )
                shift_x, shift_y, score = _estimate_reference_shift(
                    reference_work,
                    working_current,
                )
                if score < _BURST_ENHANCE_MIN_SCORE:
                    continue
                if (
                    abs(shift_x) > _BURST_ENHANCE_MAX_SHIFT_PX
                    or abs(shift_y) > _BURST_ENHANCE_MAX_SHIFT_PX
                ):
                    continue
                if shift_x or shift_y:
                    reference_work = _apply_translation_crop(
                        reference_work, shift_x, shift_y
                    )
                frames.append(np.asarray(reference_work, dtype=np.float32))
                accepted_references += 1
        except Exception as exc:
            logging.debug(
                "[%s] Burst enhance skipped reference %s: %s", name, path, exc
            )

    fused_array, fusion_label = _fuse_burst_frames(frames, profile)
    enhanced = Image.fromarray(fused_array.astype(np.uint8))

    if mode == "full_frame":
        if max(image.size) <= _BURST_ENHANCE_LOWDEF_UPSCALE_MAX_DIM:
            output_size = (image.size[0] * 2, image.size[1] * 2)
        else:
            output_size = image.size
    else:
        output_size = image.size

    if enhanced.size != output_size:
        enhanced = enhanced.resize(output_size, _PIL_RESAMPLING.LANCZOS)

    normalized_profile = _normalize_burst_enhance_profile(profile)
    if normalized_profile == "crisp":
        enhanced = enhanced.filter(
            ImageFilter.UnsharpMask(radius=1.2, percent=130, threshold=2)
        )

    logging.info(
        "[%s] Applied burst enhance mode=%s profile=%s fusion=%s refs=%d output=%sx%s",
        name,
        mode,
        normalized_profile,
        fusion_label,
        accepted_references,
        enhanced.size[0],
        enhanced.size[1],
    )
    return enhanced


def _night_enhance_captured_image(
    image: Image.Image,
    final_path: str,
    name: str,
    mode: str | None,
) -> Image.Image:
    """Lift dark static stills using nearby night frames for denoise."""

    normalized_mode = _normalize_night_enhance_mode(mode)
    if normalized_mode == "off":
        return image

    current_rgb = image.convert("RGB")
    current_array = np.asarray(current_rgb, dtype=np.float32)
    current_luma = (
        current_array[..., 0] * 0.299
        + current_array[..., 1] * 0.587
        + current_array[..., 2] * 0.114
    )
    mean_luma = float(current_luma.mean())
    bright_ratio = float((current_luma >= 170.0).mean())
    if (
        mean_luma >= _NIGHT_ENHANCE_TRIGGER_MEAN
        and bright_ratio >= _NIGHT_ENHANCE_TRIGGER_BRIGHT_RATIO
    ):
        return image

    frames: list[np.ndarray] = [current_array]
    accepted_references = 0
    for path in _collect_burst_reference_paths(final_path):
        try:
            with Image.open(path) as reference_image:
                reference_work = reference_image.convert("RGB")
                if reference_work.size != current_rgb.size:
                    reference_work = reference_work.resize(
                        current_rgb.size, _PIL_RESAMPLING.LANCZOS
                    )
                reference_work = _neutralize_reference_overlay(
                    reference_work,
                    current_rgb,
                )
                shift_x, shift_y, score = _estimate_reference_shift(
                    reference_work,
                    current_rgb,
                )
                if score < _NIGHT_ENHANCE_MIN_SCORE:
                    continue
                if (
                    abs(shift_x) > _NIGHT_ENHANCE_MAX_SHIFT_PX
                    or abs(shift_y) > _NIGHT_ENHANCE_MAX_SHIFT_PX
                ):
                    continue
                if shift_x or shift_y:
                    reference_work = _apply_translation_crop(
                        reference_work, shift_x, shift_y
                    )
                frames.append(np.asarray(reference_work, dtype=np.float32))
                accepted_references += 1
        except Exception as exc:
            logging.debug(
                "[%s] Night enhance skipped reference %s: %s", name, path, exc
            )

    base_array = (
        np.median(np.stack(frames, axis=0), axis=0).clip(0, 255).astype(np.uint8)
    )
    base_image = Image.fromarray(base_array, mode="RGB").convert("YCbCr")
    y_channel, cb_channel, cr_channel = base_image.split()

    lifted = ImageOps.autocontrast(
        y_channel,
        cutoff=_NIGHT_ENHANCE_AUTOCONTRAST[normalized_mode],
    )
    gamma = _NIGHT_ENHANCE_GAMMA[normalized_mode]
    gamma_table = [
        min(255, int(round(((value / 255.0) ** gamma) * 255.0))) for value in range(256)
    ]
    lifted = lifted.point(gamma_table)
    radius, percent, threshold = _NIGHT_ENHANCE_UNSHARP[normalized_mode]
    lifted = lifted.filter(
        ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold)
    )

    original_y = np.asarray(y_channel, dtype=np.float32)
    lifted_y = np.asarray(lifted, dtype=np.float32)
    shadow_weight = np.clip((112.0 - original_y) / 112.0, 0.0, 1.0)
    blend = _NIGHT_ENHANCE_BLEND[normalized_mode]
    blended_y = original_y * (1.0 - shadow_weight * blend) + lifted_y * (
        shadow_weight * blend
    )
    floor_lift = original_y + shadow_weight * _NIGHT_ENHANCE_FLOOR_LIFT[normalized_mode]
    blended_y = np.maximum(blended_y, floor_lift)
    merged = Image.merge(
        "YCbCr",
        (
            Image.fromarray(np.clip(blended_y, 0, 255).astype(np.uint8), mode="L"),
            cb_channel,
            cr_channel,
        ),
    ).convert("RGB")

    logging.info(
        "[%s] Applied night enhance mode=%s refs=%d mean=%.1f bright_ratio=%.3f",
        name,
        normalized_mode,
        accepted_references,
        mean_luma,
        bright_ratio,
    )
    return merged


def _postprocess_still_image(
    image: Image.Image,
    final_path: str,
    name: str,
    *,
    dark: bool = False,
    stabilize_mode: str = "off",
    remove_bg: bool = True,
) -> Image.Image:
    """Apply the shared still-image enhancement pipeline before timestamping.

    This keeps direct downloads, PDF conversions, ffmpeg frame grabs, and
    browser screenshots on the same post-processing path so stabilization and
    burst enhancement behave consistently across capture backends.

    The ``dark`` flag is intentionally *not* applied as a pixel transform here.
    Browser capture paths already honor it as a rendering hint via Chrome's
    dark-mode emulation. Applying the old still-image inversion here corrupts
    ordinary camera frames by turning true blacks into white/near-white areas.
    """

    try:
        from app.utils.template_manager import get_template

        # Capture workers can outlive UI edits; read current per-camera settings.
        template_settings = get_template(name) or {}
    except Exception as exc:
        logging.debug("[%s] Still postprocess template lookup failed: %s", name, exc)
        template_settings = {}

    disable_autocrop = template_settings.get("disable_autocrop", False)
    if isinstance(disable_autocrop, str):
        disable_autocrop = disable_autocrop.strip().lower() in {
            "true",
            "1",
            "t",
            "y",
            "yes",
            "on",
        }
    else:
        disable_autocrop = bool(disable_autocrop)

    image = image.convert("RGB")
    image = _crop_captured_image(
        image,
        template_settings.get("capture_crop_roi"),
        name,
    )
    image = _rotate_captured_image(
        image,
        template_settings.get("capture_rotate_degrees"),
        name,
    )
    image = _correct_lens_captured_image(
        image,
        template_settings.get("lens_correction_spec"),
        name,
    )
    image = _level_horizon_captured_image(
        image,
        template_settings.get("horizon_level_mode"),
        template_settings.get("horizon_level_roi"),
        final_path,
        name,
    )
    if remove_bg and not disable_autocrop:
        image = remove_background(image)
    if _static_chart_dark_mode_enabled(name, template_settings, dark):
        image = _darken_static_chart_image(image, name)
    image = _stabilize_captured_image(image, final_path, name, stabilize_mode)
    image = _night_enhance_captured_image(
        image,
        final_path,
        name,
        template_settings.get("night_enhance_mode"),
    )
    image = _enhance_captured_image(
        image,
        final_path,
        name,
        template_settings.get("burst_enhance_mode"),
        template_settings.get("burst_enhance_profile"),
        template_settings.get("burst_enhance_roi"),
    )
    return _render_composite_view(
        image,
        template_settings.get("composite_view_mode"),
        template_settings.get("composite_view_spec"),
        name,
    )


def _stabilize_captured_image(
    image: Image.Image,
    final_path: str,
    name: str,
    stabilize_mode: str | None,
) -> Image.Image:
    """Align ``image`` against recent captures for nearly static cameras."""

    mode = _normalize_stabilize_mode(stabilize_mode)
    if mode == "off":
        return image

    reference_paths = _collect_stabilization_reference_paths(final_path, mode)
    if not reference_paths:
        return image

    try:
        current_sample, scale_x, scale_y = _sample_grayscale(image)
        sample_size = (current_sample.shape[1], current_sample.shape[0])
        # Average a few nearby frames into one reference so brief foreground
        # motion does not dominate the alignment target.
        reference_sample = _build_reference_sample(reference_paths, sample_size)
        if reference_sample is None:
            return image

        max_shift_px = _STABILIZE_MAX_SHIFT_PX.get(mode, 24)
        sample_shift = max(1, int(round(max_shift_px / max(scale_x, scale_y, 1.0))))
        shift_dx, shift_dy, score = _estimate_translation(
            current_sample,
            reference_sample,
            sample_shift,
        )
        if score < _STABILIZE_SCORE_MIN:
            logging.debug(
                "[%s] Stabilize skipped; low confidence score=%.3f mode=%s",
                name,
                score,
                mode,
            )
            return image

        shift_x = int(round(-shift_dx * scale_x))
        shift_y = int(round(-shift_dy * scale_y))
        if shift_x == 0 and shift_y == 0:
            return image
        if abs(shift_x) > max_shift_px or abs(shift_y) > max_shift_px:
            logging.debug(
                "[%s] Stabilize skipped; shift too large dx=%s dy=%s mode=%s",
                name,
                shift_x,
                shift_y,
                mode,
            )
            return image

        stabilized = _apply_translation_crop(image, shift_x, shift_y)
        logging.info(
            "[%s] Applied stabilize mode=%s dx=%s dy=%s score=%.3f refs=%d",
            name,
            mode,
            shift_x,
            shift_y,
            score,
            len(reference_paths),
        )
        return stabilized
    except Exception as exc:
        logging.warning("[%s] Stabilize failed: %s", name, exc)
        return image


def check_user_activity(timeout: int = 10) -> bool:
    """Return True if the user is active within the timeout.

    Args:
        timeout (int): Seconds to wait for user input.

    Returns:
        bool: True if activity is detected.
    """

    user_activity._safe_import_pynput = _safe_import_pynput
    user_activity.idle_seconds_x11 = idle_seconds_x11
    user_activity.idle_seconds_loginctl = idle_seconds_loginctl
    user_activity.idle_seconds_windows = idle_seconds_windows
    user_activity.idle_seconds_macos = idle_seconds_macos
    user_activity.keyboard = keyboard
    user_activity.mouse = mouse
    return user_activity.check_user_activity(timeout)


STATUS_CACHE_PATH = status_cache.STATUS_CACHE_PATH
STATUS_CACHE_TTL = status_cache.STATUS_CACHE_TTL
status_code_cache = status_cache.status_code_cache
status_code_cache_time = status_cache.status_code_cache_time


def _load_status_cache() -> None:
    """Load cached HTTP status codes from disk."""

    status_cache.STATUS_CACHE_PATH = STATUS_CACHE_PATH
    status_cache._load_status_cache()


def _persist_status_cache() -> None:
    """Persist cached HTTP status codes to disk."""

    status_cache.STATUS_CACHE_PATH = STATUS_CACHE_PATH
    status_cache._persist_status_cache()


def get_cached_status_code(url: str) -> int | None:
    """Return cached HTTP status for a URL if available.

    Args:
        url (str): Target URL.

    Returns:
        int | None: Cached status or ``None`` if missing.
    """

    status_cache.STATUS_CACHE_PATH = STATUS_CACHE_PATH
    return status_cache.get_cached_status_code(url)


def set_cached_status_code(url: str, code: int) -> None:
    """Store the HTTP status code for the given URL."""

    status_cache.STATUS_CACHE_PATH = STATUS_CACHE_PATH
    status_cache.set_cached_status_code(url, code)


_load_status_cache()

FFMPEG_AVAILABLE: bool | None = None
FFPROBE_AVAILABLE: bool | None = None
# Lossless level 3 avoids excessive encoding CPU on frequently rewritten frames.
CAPTURE_PNG_COMPRESSION_LEVEL = 3

CAPTURE_STALE_PREVIOUS = "stale_previous_frame"
CAPTURE_SOURCE_UNCHANGED = "source_checked_unchanged"
CAPTURE_STALE_BROWSER_SLOT_BUSY = "stale_previous_frame_browser_slot_busy"


def is_stale_capture_result(result) -> bool:
    """Return True when capture preserved an older usable frame."""

    return result in {
        CAPTURE_STALE_PREVIOUS,
        CAPTURE_STALE_BROWSER_SLOT_BUSY,
        CAPTURE_SOURCE_UNCHANGED,
    }


last_camera_test = {}
last_camera_test_time = {}
last_camera_header = {}
last_camera_header_time = {}
last_camera_header_expiry = {}
last_camera_light = {}
last_camera_light_time = {}
lurl_cache = {}
lurl_cache_time = {}
throttle_cache = {}
last_modified_cache = {}
etag_cache = {}
etag_flip_cache = {}
accept_ranges_cache = {}
accept_ranges_cache_time = {}
dns_cache = {}
dns_cache_time = {}
dns_resolve_cache = {}
dns_resolve_cache_time = {}
tls_cache = {}
tls_cache_time = {}
redirect_cache = {}
redirect_cache_time = {}
auth_hint_cache = {}
auth_hint_cache_time = {}
redirect_loop_cache = {}
redirect_loop_cache_time = {}
content_length_cache = {}
content_length_cache_time = {}
alpn_cache = {}
alpn_cache_time = {}
alt_svc_cache = {}
alt_svc_cache_time = {}
stream_fingerprint_cache = {}
stream_fingerprint_cache_time = {}
snapshot_probe_cache = {}
snapshot_probe_cache_time = {}
rtsp_probe_cache = {}
rtsp_probe_cache_time = {}
http_error_cache = {}
http_error_cache_time = {}
auth_scheme_cache = {}
auth_scheme_cache_time = {}
auth_realm_cache = {}
auth_realm_cache_time = {}
mjpeg_probe_cache = {}
mjpeg_probe_cache_time = {}
method_pref_cache = {}
method_pref_cache_time = {}
image_hash_cache = {}
image_hash_cache_time = {}
latency_cache = {}
latency_cache_time = {}
cookie_wall_cache = {}
cookie_wall_cache_time = {}
content_mismatch_cache = {}
content_mismatch_cache_time = {}
content_anomaly_cache = {}
content_anomaly_cache_time = {}
cookie_churn_cache = {}
cookie_churn_cache_time = {}
redirect_pin_cache = {}
redirect_pin_cache_time = {}
partial_content_cache = {}
partial_content_cache_time = {}
clock_skew_cache = {}
clock_skew_cache_time = {}
h3_downgrade_cache = {}
h3_downgrade_cache_time = {}
h2_downgrade_cache = {}
h2_downgrade_cache_time = {}
static_asset_cache = {}
static_asset_cache_time = {}
html_stable_cache = {}
html_stable_cache_time = {}
codec_cache = {}
codec_cache_time = {}
rtsp_auth_cache = {}
rtsp_auth_cache_time = {}
rtsp_sdp_cache = {}
rtsp_sdp_cache_time = {}
rtsp_transport_cache = {}
rtsp_transport_cache_time = {}
rtsp_keepalive_cache = {}
rtsp_keepalive_cache_time = {}
rtsp_profile_cache = {}
rtsp_profile_cache_time = {}
reachability_cache = {}
domain_backoff_cache = {}
local_quarantine_cache = {}
_tier_failure_log_cache: dict[str, dict[str, float]] = {}
TIER_FAILURE_LOG_INTERVAL_SECONDS = 30
danger_fallback_cache = {}
danger_session_cache = {}
_local_quarantine_log_cache: dict[str, float] = {}
_domain_backoff_log_cache: dict[str, float] = {}
_wan_offline_log_cache: dict[str, float] = {}
source_circuit_cache = {}
_source_circuit_log_cache: dict[str, float] = {}
domain_retry_budget_cache = {}

PREFLIGHT_CACHE_PATH = "data/preflight_cache.json"
PREFLIGHT_CACHE_PERSIST_EVERY = 60
PREFLIGHT_MAX_BYTES = int(os.getenv("PREFLIGHT_MAX_BYTES", str(50 * 1024 * 1024)))
PREFLIGHT_REACHABILITY_TTL = int(os.getenv("PREFLIGHT_REACHABILITY_TTL", "120"))
PREFLIGHT_REACHABILITY_BACKOFF = int(os.getenv("PREFLIGHT_REACHABILITY_BACKOFF", "120"))
PREFLIGHT_RTSP_PROBE_TTL = int(os.getenv("PREFLIGHT_RTSP_PROBE_TTL", "1800"))
PREFLIGHT_RTSP_KEEPALIVE_TTL = int(os.getenv("PREFLIGHT_RTSP_KEEPALIVE_TTL", "600"))
PREFLIGHT_DNS_CACHE_TTL = int(os.getenv("PREFLIGHT_DNS_CACHE_TTL", "3600"))
PREFLIGHT_TLS_CACHE_TTL = int(os.getenv("PREFLIGHT_TLS_CACHE_TTL", "3600"))
PREFLIGHT_DNS_RESOLVE_TTL = int(os.getenv("PREFLIGHT_DNS_RESOLVE_TTL", "3600"))
PREFLIGHT_RENDERER_FAIL_TTL = int(os.getenv("PREFLIGHT_RENDERER_FAIL_TTL", "900"))
PREFLIGHT_HTML_STABLE_THRESHOLD = int(os.getenv("PREFLIGHT_HTML_STABLE_THRESHOLD", "3"))
PREFLIGHT_HTML_STABLE_WINDOW = int(os.getenv("PREFLIGHT_HTML_STABLE_WINDOW", "3600"))
PREFLIGHT_HTML_STABLE_BACKOFF = int(os.getenv("PREFLIGHT_HTML_STABLE_BACKOFF", "1800"))
PREFLIGHT_HTML_MAX_BYTES = int(os.getenv("PREFLIGHT_HTML_MAX_BYTES", "5000000"))
PREFLIGHT_H2_DOWNGRADE_TTL = int(os.getenv("PREFLIGHT_H2_DOWNGRADE_TTL", "3600"))
PREFLIGHT_FFMPEG_NULL_PROBE = (
    os.getenv("PREFLIGHT_FFMPEG_NULL_PROBE", "true").lower() == "true"
)
PREFLIGHT_YTDLP_SIMULATE = (
    os.getenv("PREFLIGHT_YTDLP_SIMULATE", "true").lower() == "true"
)
IMAGE_HASH_MAX_BYTES = int(os.getenv("IMAGE_HASH_MAX_BYTES", str(256 * 1024)))
MAX_REDIRECTS = 5
DOMAIN_CONCURRENCY_LIMIT = int(os.getenv("DOMAIN_CONCURRENCY_LIMIT", "2"))
PRELIGHT_LATENCY_THRESHOLD = float(os.getenv("PREFLIGHT_LATENCY_THRESHOLD", "5.0"))
LOCAL_QUARANTINE_LOG_INTERVAL = int(os.getenv("LOCAL_QUARANTINE_LOG_INTERVAL", "60"))
DOMAIN_BACKOFF_LOG_INTERVAL = int(os.getenv("DOMAIN_BACKOFF_LOG_INTERVAL", "90"))
WAN_OFFLINE_LOG_INTERVAL = int(os.getenv("WAN_OFFLINE_LOG_INTERVAL", "120"))
PREFLIGHT_BACKOFF_WAN_OFFLINE = int(
    os.getenv("PREFLIGHT_BACKOFF_WAN_OFFLINE", str(60 * 10))
)
SOURCE_CIRCUIT_THRESHOLD = int(os.getenv("SOURCE_CIRCUIT_THRESHOLD", "5"))
SOURCE_CIRCUIT_WINDOW_SECONDS = int(os.getenv("SOURCE_CIRCUIT_WINDOW_SECONDS", "900"))
SOURCE_CIRCUIT_COOLDOWN_SECONDS = int(
    os.getenv("SOURCE_CIRCUIT_COOLDOWN_SECONDS", "1800")
)
SOURCE_CIRCUIT_LOG_INTERVAL = int(os.getenv("SOURCE_CIRCUIT_LOG_INTERVAL", "120"))
DOMAIN_RETRY_BUDGET_LIMIT = int(os.getenv("DOMAIN_RETRY_BUDGET_LIMIT", "12"))
DOMAIN_RETRY_BUDGET_WINDOW_SECONDS = int(
    os.getenv("DOMAIN_RETRY_BUDGET_WINDOW_SECONDS", "300")
)
DOMAIN_RETRY_BUDGET_BACKOFF_SECONDS = int(
    os.getenv("DOMAIN_RETRY_BUDGET_BACKOFF_SECONDS", "300")
)
_preflight_cache_last_persist = 0.0


def _load_preflight_cache() -> None:
    if not os.path.exists(PREFLIGHT_CACHE_PATH):
        return
    try:
        with open(PREFLIGHT_CACHE_PATH) as f:
            data = json.load(f)
    except Exception:
        return

    accept_ranges_cache.update(data.get("accept_ranges_cache", {}))
    accept_ranges_cache_time.update(data.get("accept_ranges_cache_time", {}))
    last_camera_header.update(data.get("last_camera_header", {}))
    last_camera_header_time.update(data.get("last_camera_header_time", {}))
    last_camera_header_expiry.update(data.get("last_camera_header_expiry", {}))
    last_modified_cache.update(data.get("last_modified_cache", {}))
    etag_cache.update(data.get("etag_cache", {}))
    etag_flip_cache.update(data.get("etag_flip_cache", {}))
    dns_cache.update(data.get("dns_cache", {}))
    dns_cache_time.update(data.get("dns_cache_time", {}))
    dns_resolve_cache.update(data.get("dns_resolve_cache", {}))
    dns_resolve_cache_time.update(data.get("dns_resolve_cache_time", {}))
    tls_cache.update(data.get("tls_cache", {}))
    tls_cache_time.update(data.get("tls_cache_time", {}))
    alpn_cache.update(data.get("alpn_cache", {}))
    alpn_cache_time.update(data.get("alpn_cache_time", {}))
    alt_svc_cache.update(data.get("alt_svc_cache", {}))
    alt_svc_cache_time.update(data.get("alt_svc_cache_time", {}))
    redirect_cache.update(data.get("redirect_cache", {}))
    redirect_cache_time.update(data.get("redirect_cache_time", {}))
    auth_hint_cache.update(data.get("auth_hint_cache", {}))
    auth_hint_cache_time.update(data.get("auth_hint_cache_time", {}))
    redirect_loop_cache.update(data.get("redirect_loop_cache", {}))
    redirect_loop_cache_time.update(data.get("redirect_loop_cache_time", {}))
    content_length_cache.update(data.get("content_length_cache", {}))
    content_length_cache_time.update(data.get("content_length_cache_time", {}))
    stream_fingerprint_cache.update(data.get("stream_fingerprint_cache", {}))
    stream_fingerprint_cache_time.update(data.get("stream_fingerprint_cache_time", {}))
    snapshot_probe_cache.update(data.get("snapshot_probe_cache", {}))
    snapshot_probe_cache_time.update(data.get("snapshot_probe_cache_time", {}))
    rtsp_probe_cache.update(data.get("rtsp_probe_cache", {}))
    rtsp_probe_cache_time.update(data.get("rtsp_probe_cache_time", {}))
    http_error_cache.update(data.get("http_error_cache", {}))
    http_error_cache_time.update(data.get("http_error_cache_time", {}))
    auth_scheme_cache.update(data.get("auth_scheme_cache", {}))
    auth_scheme_cache_time.update(data.get("auth_scheme_cache_time", {}))
    auth_realm_cache.update(data.get("auth_realm_cache", {}))
    auth_realm_cache_time.update(data.get("auth_realm_cache_time", {}))
    mjpeg_probe_cache.update(data.get("mjpeg_probe_cache", {}))
    mjpeg_probe_cache_time.update(data.get("mjpeg_probe_cache_time", {}))
    method_pref_cache.update(data.get("method_pref_cache", {}))
    method_pref_cache_time.update(data.get("method_pref_cache_time", {}))
    image_hash_cache.update(data.get("image_hash_cache", {}))
    image_hash_cache_time.update(data.get("image_hash_cache_time", {}))
    latency_cache.update(data.get("latency_cache", {}))
    latency_cache_time.update(data.get("latency_cache_time", {}))
    cookie_wall_cache.update(data.get("cookie_wall_cache", {}))
    cookie_wall_cache_time.update(data.get("cookie_wall_cache_time", {}))
    content_mismatch_cache.update(data.get("content_mismatch_cache", {}))
    content_mismatch_cache_time.update(data.get("content_mismatch_cache_time", {}))
    content_anomaly_cache.update(data.get("content_anomaly_cache", {}))
    content_anomaly_cache_time.update(data.get("content_anomaly_cache_time", {}))
    cookie_churn_cache.update(data.get("cookie_churn_cache", {}))
    cookie_churn_cache_time.update(data.get("cookie_churn_cache_time", {}))
    redirect_pin_cache.update(data.get("redirect_pin_cache", {}))
    redirect_pin_cache_time.update(data.get("redirect_pin_cache_time", {}))
    partial_content_cache.update(data.get("partial_content_cache", {}))
    partial_content_cache_time.update(data.get("partial_content_cache_time", {}))
    clock_skew_cache.update(data.get("clock_skew_cache", {}))
    clock_skew_cache_time.update(data.get("clock_skew_cache_time", {}))
    h3_downgrade_cache.update(data.get("h3_downgrade_cache", {}))
    h3_downgrade_cache_time.update(data.get("h3_downgrade_cache_time", {}))
    h2_downgrade_cache.update(data.get("h2_downgrade_cache", {}))
    h2_downgrade_cache_time.update(data.get("h2_downgrade_cache_time", {}))
    static_asset_cache.update(data.get("static_asset_cache", {}))
    static_asset_cache_time.update(data.get("static_asset_cache_time", {}))
    html_stable_cache.update(data.get("html_stable_cache", {}))
    html_stable_cache_time.update(data.get("html_stable_cache_time", {}))
    codec_cache.update(data.get("codec_cache", {}))
    codec_cache_time.update(data.get("codec_cache_time", {}))
    rtsp_auth_cache.update(data.get("rtsp_auth_cache", {}))
    rtsp_auth_cache_time.update(data.get("rtsp_auth_cache_time", {}))
    rtsp_sdp_cache.update(data.get("rtsp_sdp_cache", {}))
    rtsp_sdp_cache_time.update(data.get("rtsp_sdp_cache_time", {}))
    rtsp_transport_cache.update(data.get("rtsp_transport_cache", {}))
    rtsp_transport_cache_time.update(data.get("rtsp_transport_cache_time", {}))
    rtsp_keepalive_cache.update(data.get("rtsp_keepalive_cache", {}))
    rtsp_keepalive_cache_time.update(data.get("rtsp_keepalive_cache_time", {}))
    rtsp_profile_cache.update(data.get("rtsp_profile_cache", {}))
    rtsp_profile_cache_time.update(data.get("rtsp_profile_cache_time", {}))
    reachability_cache.update(data.get("reachability_cache", {}))
    domain_backoff_cache.update(data.get("domain_backoff_cache", {}))
    local_quarantine_cache.update(data.get("local_quarantine_cache", {}))
    source_circuit_cache.update(data.get("source_circuit_cache", {}))
    domain_retry_budget_cache.update(data.get("domain_retry_budget_cache", {}))
    danger_fallback_cache.update(data.get("danger_fallback_cache", {}))
    danger_session_cache.update(data.get("danger_session_cache", {}))
    tier_cache.update(data.get("tier_cache", {}))
    method_backoff_cache.update(data.get("method_backoff_cache", {}))


def _persist_preflight_cache(force: bool = False) -> None:
    global _preflight_cache_last_persist
    now = time.time()
    if (
        not force
        and now - _preflight_cache_last_persist < PREFLIGHT_CACHE_PERSIST_EVERY
    ):
        return
    _preflight_cache_last_persist = now
    os.makedirs(os.path.dirname(PREFLIGHT_CACHE_PATH), exist_ok=True)
    data = {
        "accept_ranges_cache": accept_ranges_cache,
        "accept_ranges_cache_time": accept_ranges_cache_time,
        "last_camera_header": last_camera_header,
        "last_camera_header_time": last_camera_header_time,
        "last_camera_header_expiry": last_camera_header_expiry,
        "last_modified_cache": last_modified_cache,
        "etag_cache": etag_cache,
        "etag_flip_cache": etag_flip_cache,
        "dns_cache": dns_cache,
        "dns_cache_time": dns_cache_time,
        "dns_resolve_cache": dns_resolve_cache,
        "dns_resolve_cache_time": dns_resolve_cache_time,
        "tls_cache": tls_cache,
        "tls_cache_time": tls_cache_time,
        "alpn_cache": alpn_cache,
        "alpn_cache_time": alpn_cache_time,
        "alt_svc_cache": alt_svc_cache,
        "alt_svc_cache_time": alt_svc_cache_time,
        "redirect_cache": redirect_cache,
        "redirect_cache_time": redirect_cache_time,
        "auth_hint_cache": auth_hint_cache,
        "auth_hint_cache_time": auth_hint_cache_time,
        "redirect_loop_cache": redirect_loop_cache,
        "redirect_loop_cache_time": redirect_loop_cache_time,
        "content_length_cache": content_length_cache,
        "content_length_cache_time": content_length_cache_time,
        "stream_fingerprint_cache": stream_fingerprint_cache,
        "stream_fingerprint_cache_time": stream_fingerprint_cache_time,
        "snapshot_probe_cache": snapshot_probe_cache,
        "snapshot_probe_cache_time": snapshot_probe_cache_time,
        "rtsp_probe_cache": rtsp_probe_cache,
        "rtsp_probe_cache_time": rtsp_probe_cache_time,
        "http_error_cache": http_error_cache,
        "http_error_cache_time": http_error_cache_time,
        "auth_scheme_cache": auth_scheme_cache,
        "auth_scheme_cache_time": auth_scheme_cache_time,
        "auth_realm_cache": auth_realm_cache,
        "auth_realm_cache_time": auth_realm_cache_time,
        "mjpeg_probe_cache": mjpeg_probe_cache,
        "mjpeg_probe_cache_time": mjpeg_probe_cache_time,
        "method_pref_cache": method_pref_cache,
        "method_pref_cache_time": method_pref_cache_time,
        "image_hash_cache": image_hash_cache,
        "image_hash_cache_time": image_hash_cache_time,
        "latency_cache": latency_cache,
        "latency_cache_time": latency_cache_time,
        "cookie_wall_cache": cookie_wall_cache,
        "cookie_wall_cache_time": cookie_wall_cache_time,
        "content_mismatch_cache": content_mismatch_cache,
        "content_mismatch_cache_time": content_mismatch_cache_time,
        "content_anomaly_cache": content_anomaly_cache,
        "content_anomaly_cache_time": content_anomaly_cache_time,
        "cookie_churn_cache": cookie_churn_cache,
        "cookie_churn_cache_time": cookie_churn_cache_time,
        "redirect_pin_cache": redirect_pin_cache,
        "redirect_pin_cache_time": redirect_pin_cache_time,
        "partial_content_cache": partial_content_cache,
        "partial_content_cache_time": partial_content_cache_time,
        "clock_skew_cache": clock_skew_cache,
        "clock_skew_cache_time": clock_skew_cache_time,
        "h3_downgrade_cache": h3_downgrade_cache,
        "h3_downgrade_cache_time": h3_downgrade_cache_time,
        "h2_downgrade_cache": h2_downgrade_cache,
        "h2_downgrade_cache_time": h2_downgrade_cache_time,
        "static_asset_cache": static_asset_cache,
        "static_asset_cache_time": static_asset_cache_time,
        "html_stable_cache": html_stable_cache,
        "html_stable_cache_time": html_stable_cache_time,
        "codec_cache": codec_cache,
        "codec_cache_time": codec_cache_time,
        "rtsp_auth_cache": rtsp_auth_cache,
        "rtsp_auth_cache_time": rtsp_auth_cache_time,
        "rtsp_sdp_cache": rtsp_sdp_cache,
        "rtsp_sdp_cache_time": rtsp_sdp_cache_time,
        "rtsp_transport_cache": rtsp_transport_cache,
        "rtsp_transport_cache_time": rtsp_transport_cache_time,
        "rtsp_keepalive_cache": rtsp_keepalive_cache,
        "rtsp_keepalive_cache_time": rtsp_keepalive_cache_time,
        "rtsp_profile_cache": rtsp_profile_cache,
        "rtsp_profile_cache_time": rtsp_profile_cache_time,
        "reachability_cache": reachability_cache,
        "domain_backoff_cache": domain_backoff_cache,
        "local_quarantine_cache": local_quarantine_cache,
        "source_circuit_cache": source_circuit_cache,
        "domain_retry_budget_cache": domain_retry_budget_cache,
        "danger_fallback_cache": danger_fallback_cache,
        "danger_session_cache": danger_session_cache,
        "tier_cache": tier_cache,
        "method_backoff_cache": method_backoff_cache,
    }
    try:
        with open(PREFLIGHT_CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        logging.exception("Failed to persist preflight cache")


PREFLIGHT_BACKOFF_REQUEST_FAIL = 60 * 5
PREFLIGHT_BACKOFF_STREAM_FAIL = 60 * 10
PREFLIGHT_BACKOFF_YTDLP_FAIL = 60 * 10
PREFLIGHT_BACKOFF_BROWSER_FAIL = 60 * 15
HUBITAT_CLOUD_DASHBOARD_FAILURE_REASONS = {
    "hubitat_blank_dashboard",
    "hubitat_gateway_timeout",
    "hubitat_no_response_from_hub",
}
PREFLIGHT_BACKOFF_LOCAL_UNREACHABLE = int(
    os.getenv("PREFLIGHT_BACKOFF_LOCAL_UNREACHABLE", "600")
)
RTSP_PREFLIGHT_FAIL_THRESHOLD = int(os.getenv("RTSP_PREFLIGHT_FAIL_THRESHOLD", "3"))
RTSP_PREFLIGHT_FAIL_WINDOW_SECONDS = int(
    os.getenv("RTSP_PREFLIGHT_FAIL_WINDOW_SECONDS", "900")
)
RTSP_PREFLIGHT_BACKOFF_SECONDS = int(
    os.getenv("RTSP_PREFLIGHT_BACKOFF_SECONDS", "3600")
)
DANGER_FALLBACK_THRESHOLD = int(os.getenv("DANGER_FALLBACK_THRESHOLD", "3"))
DANGER_FALLBACK_WINDOW_SECONDS = int(os.getenv("DANGER_FALLBACK_WINDOW_SECONDS", "600"))
DANGER_FALLBACK_FORCE_SECONDS = int(os.getenv("DANGER_FALLBACK_FORCE_SECONDS", "600"))
DANGER_FALLBACK_BACKOFF_SECONDS = int(
    os.getenv("DANGER_FALLBACK_BACKOFF_SECONDS", "900")
)
DANGER_FALLBACK_LOG_THROTTLE = int(os.getenv("DANGER_FALLBACK_LOG_THROTTLE", "600"))
PREFLIGHT_BACKOFF_DOMAIN_AUTH = int(os.getenv("PREFLIGHT_BACKOFF_DOMAIN_AUTH", "600"))
PREFLIGHT_BACKOFF_DOMAIN_NOT_FOUND = int(
    os.getenv("PREFLIGHT_BACKOFF_DOMAIN_NOT_FOUND", "1800")
)
PREFLIGHT_BACKOFF_DOMAIN_LOCAL_FAIL = int(
    os.getenv("PREFLIGHT_BACKOFF_DOMAIN_LOCAL_FAIL", "900")
)
PREFLIGHT_LOCAL_QUARANTINE_THRESHOLD = int(
    os.getenv("PREFLIGHT_LOCAL_QUARANTINE_THRESHOLD", "5")
)
PREFLIGHT_LOCAL_QUARANTINE_WINDOW = int(
    os.getenv("PREFLIGHT_LOCAL_QUARANTINE_WINDOW", "900")
)
PREFLIGHT_LOCAL_QUARANTINE_BACKOFF = int(
    os.getenv("PREFLIGHT_LOCAL_QUARANTINE_BACKOFF", "3600")
)
PREFLIGHT_LAN_FAST_PROBE_TIMEOUT = float(
    os.getenv("PREFLIGHT_LAN_FAST_PROBE_TIMEOUT", "1.0")
)
PREFLIGHT_LOW_CPU_LOCAL_BUDGET_SECONDS = int(
    os.getenv("PREFLIGHT_LOW_CPU_LOCAL_BUDGET_SECONDS", "3")
)
PREFLIGHT_LOW_CPU_WAN_BUDGET_SECONDS = int(
    os.getenv("PREFLIGHT_LOW_CPU_WAN_BUDGET_SECONDS", "5")
)
# RTSP streams across WAN links can take longer than a few seconds to respond
# (DNS, TCP handshake, auth challenge, initial keyframe). Keep this tunable.
STREAM_PROBE_TIMEOUT = int(os.getenv("STREAM_PROBE_TIMEOUT", "10"))
HDHOMERUN_URL_RE = re.compile(r"/auto/v\d+(?:\.\d+)?(?:$|[/?#])", re.IGNORECASE)

TIER_OFFLINE = 0
TIER_NETWORK = 1
TIER_HTTP = 2
TIER_LIGHT_RENDER = 3
TIER_HEADLESS = 4
TIER_CONTROLLED = 5
TIER_DEVICE = 6
TIER_HUMAN = 7

TIER_NAMES = {
    TIER_OFFLINE: "offline",
    TIER_NETWORK: "network",
    TIER_HTTP: "http",
    TIER_LIGHT_RENDER: "light_render",
    TIER_HEADLESS: "headless",
    TIER_CONTROLLED: "controlled",
    TIER_DEVICE: "device",
    TIER_HUMAN: "human",
}

SUPPORTED_STREAM_CODECS = {"h264", "h265", "hevc", "mpeg4", "vp8"}
LOCAL_FAILURE_REASONS = {
    "unreachable",
    "lan_offline",
    "rtsp_unreachable",
    "rtsp_describe_failed",
    "stream_capture_failed",
    "image_download_failed",
    "pdf_download_failed",
    "mjpeg_probe_failed",
    "ffprobe_failed",
    "request_failed",
    "offline",
    "dns_offline",
}
PREFLIGHT_CONTENT_ANOMALY_THRESHOLD = int(
    os.getenv("PREFLIGHT_CONTENT_ANOMALY_THRESHOLD", "2")
)
PREFLIGHT_CONTENT_ANOMALY_WINDOW = int(
    os.getenv("PREFLIGHT_CONTENT_ANOMALY_WINDOW", "3600")
)
PREFLIGHT_CONTENT_ANOMALY_BACKOFF = int(
    os.getenv("PREFLIGHT_CONTENT_ANOMALY_BACKOFF", "7200")
)
REDIRECT_CHAIN_REPEAT_THRESHOLD = int(os.getenv("REDIRECT_CHAIN_REPEAT_THRESHOLD", "2"))
PREFLIGHT_REDIRECT_PIN_TTL = int(os.getenv("PREFLIGHT_REDIRECT_PIN_TTL", "3600"))
PREFLIGHT_PARTIAL_CONTENT_MIN_BYTES = int(
    os.getenv("PREFLIGHT_PARTIAL_CONTENT_MIN_BYTES", "1024")
)
PREFLIGHT_PARTIAL_CONTENT_THRESHOLD = int(
    os.getenv("PREFLIGHT_PARTIAL_CONTENT_THRESHOLD", "3")
)
PREFLIGHT_PARTIAL_CONTENT_WINDOW = int(
    os.getenv("PREFLIGHT_PARTIAL_CONTENT_WINDOW", "3600")
)
PREFLIGHT_PARTIAL_CONTENT_BACKOFF = int(
    os.getenv("PREFLIGHT_PARTIAL_CONTENT_BACKOFF", "7200")
)
PREFLIGHT_CLOCK_SKEW_SECONDS = int(os.getenv("PREFLIGHT_CLOCK_SKEW_SECONDS", "900"))
PREFLIGHT_SNIFF_BYTES = int(os.getenv("PREFLIGHT_SNIFF_BYTES", "1024"))
PREFLIGHT_H3_DOWNGRADE_TTL = int(os.getenv("PREFLIGHT_H3_DOWNGRADE_TTL", "3600"))
PREFLIGHT_FORCE_H3_DOWNGRADE = (
    os.getenv("PREFLIGHT_FORCE_H3_DOWNGRADE", "false").lower() == "true"
)
PREFLIGHT_ETAG_FLIP_THRESHOLD = int(os.getenv("PREFLIGHT_ETAG_FLIP_THRESHOLD", "5"))
PREFLIGHT_ETAG_FLIP_WINDOW = int(os.getenv("PREFLIGHT_ETAG_FLIP_WINDOW", "3600"))
PREFLIGHT_ETAG_FLIP_BACKOFF = int(os.getenv("PREFLIGHT_ETAG_FLIP_BACKOFF", "1800"))
PREFLIGHT_CONTENT_LENGTH_MAX_VARIANCE = float(
    os.getenv("PREFLIGHT_CONTENT_LENGTH_MAX_VARIANCE", "0.5")
)
PREFLIGHT_COOKIE_CHURN_THRESHOLD = int(
    os.getenv("PREFLIGHT_COOKIE_CHURN_THRESHOLD", "3")
)
PREFLIGHT_COOKIE_CHURN_WINDOW = int(os.getenv("PREFLIGHT_COOKIE_CHURN_WINDOW", "3600"))
PREFLIGHT_COOKIE_CHURN_BACKOFF = int(
    os.getenv("PREFLIGHT_COOKIE_CHURN_BACKOFF", "3600")
)
PREFLIGHT_STATIC_ASSET_THRESHOLD = int(
    os.getenv("PREFLIGHT_STATIC_ASSET_THRESHOLD", "4")
)
PREFLIGHT_STATIC_ASSET_WINDOW = int(
    os.getenv(
        "PREFLIGHT_STATIC_ASSET_WINDOW",
        os.getenv("STATIC_ASSET_ETAG_STABLE_WINDOW", "7200"),
    )
)
PREFLIGHT_STATIC_ASSET_BACKOFF = int(
    os.getenv("PREFLIGHT_STATIC_ASSET_BACKOFF", "7200")
)

TIER_ESCALATION_LOCK_SECONDS = {
    TIER_LIGHT_RENDER: 15 * 60,
    TIER_HEADLESS: 30 * 60,
    TIER_CONTROLLED: 60 * 60,
    TIER_DEVICE: 2 * 60 * 60,
    TIER_HUMAN: 2 * 60 * 60,
}

tier_cache = {}
method_backoff_cache = {}
domain_active = {}
domain_lock = threading.Lock()

LIGHT_RENDER_BACKOFF_BASE = 5 * 60
PHANTOM_BACKOFF_BASE = 10 * 60
HEADLESS_BACKOFF_BASE = 15 * 60
STREAM_BACKOFF_BASE = 10 * 60
YTDLP_BACKOFF_BASE = 10 * 60
BACKOFF_MAX_SECONDS = 2 * 60 * 60

_load_preflight_cache()


def _check_ffmpeg() -> bool:
    """Return ``True`` if ``ffmpeg`` executable is available."""

    global FFMPEG_AVAILABLE
    if FFMPEG_AVAILABLE is None:
        FFMPEG_AVAILABLE = shutil.which(FFMPEG_PATH) is not None
        if not FFMPEG_AVAILABLE:
            logging.error("ffmpeg not found at %s", FFMPEG_PATH)
    return FFMPEG_AVAILABLE


def _check_ffprobe() -> bool:
    """Return ``True`` if ``ffprobe`` executable is available."""

    global FFPROBE_AVAILABLE
    if FFPROBE_AVAILABLE is None:
        FFPROBE_AVAILABLE = shutil.which(FFPROBE_PATH) is not None
        if not FFPROBE_AVAILABLE:
            logging.error("ffprobe not found at %s", FFPROBE_PATH)
    return FFPROBE_AVAILABLE


def _is_hdhomerun_like_stream_url(url: str) -> bool:
    """Return ``True`` when *url* looks like an HDHomeRun stream endpoint."""

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if "hdhomerun" in host:
        return True
    return bool(HDHOMERUN_URL_RE.search(parsed.path or ""))


def _probe_stream_with_ffprobe(url: str, timeout: int, name: str) -> bool:
    """Return True when ffprobe can read stream metadata."""

    if not _check_ffprobe():
        return True

    scheme = urlparse(url).scheme.lower()
    analyze_duration = ANALYZE_DURATION_DEFAULT
    probe_size = PROBE_SIZE_DEFAULT
    # Early RTSP preflight to avoid repeated stream failures later in the flow.
    if scheme in {"rtsp", "rtsps"}:
        analyze_duration = ANALYZE_DURATION_RTSP
        probe_size = PROBE_SIZE_RTSP
    elif _is_hdhomerun_like_stream_url(url):
        # HDHomeRun streams are MPEG-TS and often need a larger probe window
        # than generic HTTP image/video endpoints.
        analyze_duration = ANALYZE_DURATION_OTHER
        probe_size = PROBE_SIZE_OTHER
    elif scheme not in {"http", "https"}:
        analyze_duration = ANALYZE_DURATION_OTHER
        probe_size = PROBE_SIZE_OTHER

    base_cmd = [
        FFPROBE_PATH,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate,pix_fmt,bit_rate",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        "-analyzeduration",
        analyze_duration,
        "-probesize",
        probe_size,
    ]
    if scheme in {"rtsp", "rtsps"}:
        # Some ffprobe builds (notably Ubuntu's) do not support `-stimeout`
        # for RTSP, causing probes to fail with "Option not found". Prefer
        # `-rw_timeout` (microseconds), and rely on the subprocess timeout too.
        base_cmd.extend(["-rw_timeout", str(int(timeout * 1_000_000))])

    transports = [None]
    if scheme in {"rtsp", "rtsps"}:
        transports = _rtsp_transport_candidates(url)
    per_attempt_timeout = max(2, int(timeout / max(len(transports), 1)))
    if scheme in {"rtsp", "rtsps"}:
        # Preserve a usable per-transport budget for slower RTSP cameras.
        # Splitting a 20s template timeout across TCP+UDP fallback can turn a
        # healthy LAN camera into a false preflight timeout at 10s.
        per_attempt_timeout = max(per_attempt_timeout, min(max(timeout, 10), 20))
    last_error = None

    for transport in transports:
        cmd = list(base_cmd)
        if transport:
            cmd.extend(["-rtsp_transport", transport])
            logging.debug(
                "ffprobe RTSP transport=%s for %s", transport, sanitize_url(url)
            )
        cmd.append(url)
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=per_attempt_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = "timeout"
            continue
        except Exception as exc:
            last_error = str(exc)
            continue

        returncode = getattr(result, "returncode", 0)
        if isinstance(returncode, int) and returncode != 0:
            last_error = result.stderr.decode("utf-8", errors="replace").strip()
            continue
        try:
            payload = json.loads(result.stdout.decode("utf-8", errors="replace"))
            streams = payload.get("streams", [])
            if not isinstance(streams, list) or not streams:
                last_error = "no video stream metadata"
                continue
            stream = streams[0]
            if not isinstance(stream, dict) or not stream.get("codec_name"):
                last_error = "missing video codec metadata"
                continue
        except Exception:
            last_error = "invalid video stream metadata"
            continue
        fingerprint = {
            "codec": stream.get("codec_name"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "fps": stream.get("r_frame_rate"),
            "pix_fmt": stream.get("pix_fmt"),
            "bit_rate": stream.get("bit_rate"),
        }
        try:
            _set_stream_fingerprint(url, fingerprint)
        except Exception:
            logging.debug("ffprobe fingerprint cache failed for %s", sanitize_url(url))
        if transport:
            _set_rtsp_transport(url, transport)
        return True

    if last_error == "timeout":
        logging.error("ffprobe timed out for %s after %ss", sanitize_url(url), timeout)
    elif last_error:
        logging.error(
            "ffprobe failed for %s (%s): %s",
            sanitize_url(url),
            name,
            last_error,
        )
    else:
        logging.warning("ffprobe failed for %s: %s", sanitize_url(url), name)
    return False


def _ffmpeg_null_probe(
    url: str, timeout: int, name: str, stealth: bool = False
) -> bool:
    """Run a short ffmpeg null mux probe to validate stream decode early."""

    scheme = urlparse(url).scheme.lower()
    analyze_duration = ANALYZE_DURATION_DEFAULT
    probe_size = PROBE_SIZE_DEFAULT
    if scheme in {"rtsp", "rtsps"}:
        analyze_duration = ANALYZE_DURATION_RTSP
        probe_size = PROBE_SIZE_RTSP
    elif _is_hdhomerun_like_stream_url(url):
        analyze_duration = ANALYZE_DURATION_OTHER
        probe_size = PROBE_SIZE_OTHER
    elif scheme not in {"http", "https"}:
        analyze_duration = ANALYZE_DURATION_OTHER
        probe_size = PROBE_SIZE_OTHER

    base_cmd = [FFMPEG_PATH, "-hide_banner", "-nostdin", "-v", "error", "-xerror"]
    if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
        base_cmd.extend(["-hwaccel", FFMPEG_HWACCEL])

    lua = UA
    if stealth and scheme in {"http", "https"}:
        chrome_path = get_chrome_path()
        cv = get_chrome_version(chrome_path)
        lua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36" % cv
        )

    transports = [None]
    if scheme in {"rtsp", "rtsps"}:
        transports = _rtsp_transport_candidates(url)

    # `timeout` is already bounded by the caller; don't further clamp it here
    # or WAN/slow RTSP streams can fail preflight.
    probe_timeout = max(2, int(timeout))
    per_attempt_timeout = max(2, int(probe_timeout / max(len(transports), 1)))
    if scheme in {"rtsp", "rtsps"}:
        # Mirror ffprobe behavior so TCP/UDP fallback does not reintroduce a
        # shorter deadline than the camera's configured template timeout.
        per_attempt_timeout = max(per_attempt_timeout, min(max(probe_timeout, 10), 20))
    last_error = None

    for transport in transports:
        cmd = list(base_cmd)
        if scheme in {"http", "https"}:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            cmd.extend(["-headers", "User-Agent: %s\r\n" % lua])
            cmd.extend(["-headers", f"referer: {base_url}\r\n"])
            cmd.extend(["-headers", f"origin: {base_url}\r\n"])
            cmd.extend(["-seekable", "0"])
        elif scheme in {"rtsp", "rtsps"} and transport:
            cmd.extend(["-rtsp_transport", transport])
            logging.debug(
                "ffmpeg null probe RTSP transport=%s for %s",
                transport,
                sanitize_url(url),
            )

        cmd.extend(
            [
                "-analyzeduration",
                analyze_duration,
                "-probesize",
                probe_size,
                "-i",
                url,
                "-map",
                "0:v:0",
                "-t",
                "1",
                "-sn",
                "-an",
                "-f",
                "null",
                "-",
            ]
        )

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=per_attempt_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = "timeout"
            continue
        except Exception as exc:
            last_error = str(exc)
            continue

        returncode = getattr(result, "returncode", 0)
        if isinstance(returncode, int) and returncode != 0:
            last_error = result.stderr.decode("utf-8", errors="replace").strip()
            continue
        if transport:
            _set_rtsp_transport(url, transport)
        return True

    if last_error == "timeout":
        logging.error(
            "ffmpeg null probe timed out for %s after %ss",
            sanitize_url(url),
            probe_timeout,
        )
    elif last_error:
        logging.error(
            "ffmpeg null probe failed for %s (%s): %s",
            sanitize_url(url),
            name,
            last_error[:200],
        )
    else:
        logging.warning("ffmpeg null probe failed for %s: %s", sanitize_url(url), name)
    return False


def _tier_key(url: str) -> str:
    # Google previews share our loopback HTTP server, but each URL represents
    # an independent camera. Never let one unavailable camera lock out its peers.
    stable = stable_sdm_key_for_url(url)
    if stable:
        return stable
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.lower()
    return url.lower()


def _domain_key(url: str) -> str | None:
    stable = stable_sdm_key_for_url(url)
    if stable:
        return stable
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.lower()
    return None


def _domain_backoff_active(url: str) -> tuple[bool, str | None, int]:
    key = _domain_key(url)
    if not key:
        return False, None, 0
    entry = domain_backoff_cache.get(key, {})
    timeout = entry.get("timeout", 0)
    if timeout > time.time():
        remaining = int(timeout - time.time())
        return True, entry.get("reason"), max(remaining, 0)
    return False, None, 0


def _source_circuit_key(url: str) -> str:
    return stable_sdm_key_for_url(url) or url.lower()


def _source_circuit_active(url: str) -> tuple[bool, int]:
    key = _source_circuit_key(url)
    entry = source_circuit_cache.get(key, {})
    until = entry.get("open_until", 0)
    now = time.time()
    if until > now:
        return True, int(until - now)
    return False, 0


def _record_source_failure(url: str) -> None:
    key = _source_circuit_key(url)
    now = time.time()
    entry = source_circuit_cache.setdefault(key, {"count": 0, "window_start": now})
    window_start = entry.get("window_start", now)
    if now - window_start > SOURCE_CIRCUIT_WINDOW_SECONDS:
        entry["count"] = 0
        entry["window_start"] = now
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last_failure"] = now
    if entry["count"] >= SOURCE_CIRCUIT_THRESHOLD:
        entry["open_until"] = max(
            float(entry.get("open_until", 0)),
            now + SOURCE_CIRCUIT_COOLDOWN_SECONDS,
        )
    source_circuit_cache[key] = entry


def _record_source_success(url: str) -> None:
    key = _source_circuit_key(url)
    if key not in source_circuit_cache:
        return
    source_circuit_cache.pop(key, None)


def _consume_domain_retry_budget(url: str) -> tuple[bool, int]:
    key = _domain_key(url)
    if not key:
        return True, 0
    now = time.time()
    entry = domain_retry_budget_cache.setdefault(
        key, {"count": 0, "window_start": now, "blocked_until": 0}
    )
    blocked_until = float(entry.get("blocked_until", 0))
    if blocked_until > now:
        return False, int(blocked_until - now)

    window_start = float(entry.get("window_start", now))
    if now - window_start > DOMAIN_RETRY_BUDGET_WINDOW_SECONDS:
        entry["count"] = 0
        entry["window_start"] = now

    if int(entry.get("count", 0)) >= DOMAIN_RETRY_BUDGET_LIMIT:
        entry["blocked_until"] = now + DOMAIN_RETRY_BUDGET_BACKOFF_SECONDS
        domain_retry_budget_cache[key] = entry
        return False, DOMAIN_RETRY_BUDGET_BACKOFF_SECONDS

    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last"] = now
    domain_retry_budget_cache[key] = entry
    return True, 0


def _refund_domain_retry_budget(url: str) -> None:
    key = _domain_key(url)
    if not key:
        return
    entry = domain_retry_budget_cache.get(key)
    if not entry:
        return
    entry["count"] = max(int(entry.get("count", 0)) - 1, 0)
    entry["last_success"] = time.time()
    entry["blocked_until"] = 0
    domain_retry_budget_cache[key] = entry


def _set_domain_backoff(url: str, reason: str, backoff_seconds: int) -> None:
    key = _domain_key(url)
    if not key:
        return
    domain_backoff_cache[key] = {
        "timeout": time.time() + backoff_seconds,
        "reason": reason,
    }
    _persist_preflight_cache()


def _local_quarantine_active(url: str) -> tuple[bool, int]:
    key = _domain_key(url)
    if not key:
        return False, 0
    entry = local_quarantine_cache.get(key, {})
    until = entry.get("until", 0)
    if until > time.time():
        return True, int(until - time.time())
    return False, 0


def local_quarantine_status(url: str) -> tuple[bool, int, str | None]:
    """Return (active, remaining_seconds, reason) for a local quarantine entry."""

    key = _domain_key(url)
    if not key:
        return False, 0, None
    entry = local_quarantine_cache.get(key, {})
    until = entry.get("until", 0)
    if until > time.time():
        remaining = int(until - time.time())
        return True, max(remaining, 0), entry.get("last_reason")
    return False, 0, entry.get("last_reason")


def _record_local_failure(url: str, reason: str) -> None:
    key = _domain_key(url)
    if not key:
        return
    entry = local_quarantine_cache.setdefault(key, {"count": 0, "first": time.time()})
    now = time.time()
    if now - entry.get("first", now) > PREFLIGHT_LOCAL_QUARANTINE_WINDOW:
        entry["count"] = 0
        entry["first"] = now
    entry["count"] = entry.get("count", 0) + 1
    entry["last_reason"] = reason
    if entry["count"] >= PREFLIGHT_LOCAL_QUARANTINE_THRESHOLD:
        entry["until"] = now + PREFLIGHT_LOCAL_QUARANTINE_BACKOFF
        logging.info(
            "Local quarantine for %s (%s): %ds",
            key,
            reason,
            PREFLIGHT_LOCAL_QUARANTINE_BACKOFF,
        )
    local_quarantine_cache[key] = entry
    _persist_preflight_cache()


def clear_local_quarantine(url: str) -> bool:
    """Clear any local quarantine entry for the given URL."""

    key = _domain_key(url)
    if not key:
        return False
    if key not in local_quarantine_cache:
        return False
    local_quarantine_cache.pop(key, None)
    _persist_preflight_cache()
    return True


def clear_capture_backoff(
    url: str, username: str | None = None, password: str | None = None
) -> bool:
    """Reset retry restrictions for an explicit camera recovery request.

    Host-level restrictions are shared with the local quarantine. Image hashes,
    source timestamps, authentication, and active capture locks are preserved.
    """
    # RTSP capture inserts separately stored credentials into its connection
    # URL. Clear both cache identities without exposing either to the caller.
    resolved = _rtsp_url_with_credentials(url, username, password)
    changed = clear_capture_backoff(resolved) if resolved and resolved != url else False
    changed = clear_local_quarantine(url) or changed
    for cache, key in (
        (throttle_cache, url),
        (source_circuit_cache, _source_circuit_key(url)),
        (tier_cache, _tier_key(url)),
        (domain_backoff_cache, _domain_key(url)),
        (domain_retry_budget_cache, _domain_key(url)),
        (status_code_cache, url),
        (status_code_cache_time, url),
    ):
        if key in cache:
            cache.pop(key, None)
            changed = True
    for key in list(method_backoff_cache):
        if key.startswith(url + "|"):
            method_backoff_cache.pop(key, None)
            changed = True
    if changed:
        _persist_preflight_cache()
        _persist_status_cache()
    return changed


def _try_acquire_domain(url: str) -> bool:
    key = _domain_key(url)
    if not key or DOMAIN_CONCURRENCY_LIMIT <= 0:
        return True
    with domain_lock:
        active = domain_active.get(key, 0)
        if active >= DOMAIN_CONCURRENCY_LIMIT:
            return False
        domain_active[key] = active + 1
        return True


def _release_domain(url: str) -> None:
    key = _domain_key(url)
    if not key or DOMAIN_CONCURRENCY_LIMIT <= 0:
        return
    with domain_lock:
        active = domain_active.get(key, 0)
        if active <= 1:
            domain_active.pop(key, None)
        else:
            domain_active[key] = active - 1


def _tier_allowed(url: str, tier: int) -> bool:
    entry = tier_cache.get(_tier_key(url))
    if not entry:
        return True
    lock_until = entry.get("lock_until", 0)
    if lock_until > time.time():
        return False
    if lock_until:
        # A timed lock must allow the failed capture method to recover after
        # expiry; retaining max_tier would disable that method indefinitely.
        entry.pop("lock_until", None)
        entry.pop("max_tier", None)
    max_tier = entry.get("max_tier")
    if max_tier is None:
        return True
    return tier <= max_tier


def _record_tier_success(url: str, tier: int, detail: str) -> None:
    key = _tier_key(url)
    entry = tier_cache.setdefault(key, {})
    entry["last_tier"] = tier
    entry["last_result"] = "success"
    entry["last_detail"] = detail
    entry["last_time"] = time.time()
    entry.pop("max_tier", None)
    entry.pop("lock_until", None)
    _record_source_success(url)
    _refund_domain_retry_budget(url)
    _persist_preflight_cache()


def _record_tier_failure(
    url: str, tier: int, detail: str, *, lock: bool = True
) -> None:
    key = _tier_key(url)
    entry = tier_cache.setdefault(key, {})
    entry["last_tier"] = tier
    entry["last_result"] = "failure"
    entry["last_detail"] = detail
    entry["last_time"] = time.time()
    if tier >= TIER_LIGHT_RENDER and lock:
        entry["max_tier"] = min(entry.get("max_tier", tier - 1), tier - 1)
        lock_seconds = TIER_ESCALATION_LOCK_SECONDS.get(
            tier, PREFLIGHT_BACKOFF_BROWSER_FAIL
        )
        entry["lock_until"] = time.time() + lock_seconds
    hostname = urlparse(url).hostname
    if _is_private_host(hostname) and detail in LOCAL_FAILURE_REASONS:
        _set_domain_backoff(url, f"local_{detail}", PREFLIGHT_BACKOFF_DOMAIN_LOCAL_FAIL)
        _record_local_failure(url, detail)
    if detail not in {"source_circuit_open", "retry_budget_exhausted"}:
        _record_source_failure(url)
    now = time.time()
    log_key = f"{tier}|{detail}|{sanitize_url(url)}"
    entry_log = _tier_failure_log_cache.get(log_key, {"last": 0.0, "suppressed": 0.0})
    last = float(entry_log.get("last", 0.0) or 0.0)
    if now - last >= TIER_FAILURE_LOG_INTERVAL_SECONDS:
        suppressed = int(entry_log.get("suppressed", 0) or 0)
        entry_log["last"] = now
        entry_log["suppressed"] = 0
        _tier_failure_log_cache[log_key] = entry_log
        suffix = f" (suppressed {suppressed} repeats)" if suppressed else ""
        logging.info(
            "Tier %s failed for %s: %s%s",
            TIER_NAMES.get(tier, str(tier)),
            sanitize_url(url),
            detail,
            suffix,
        )
    else:
        entry_log["suppressed"] = float(entry_log.get("suppressed", 0.0) or 0.0) + 1
        _tier_failure_log_cache[log_key] = entry_log
    _persist_preflight_cache()


def _method_key(url: str, method: str) -> str:
    return f"{url}|{method}"


def _method_allowed(url: str, method: str) -> bool:
    entry = method_backoff_cache.get(_method_key(url, method))
    if not entry:
        return True
    return entry.get("until", 0) <= time.time()


def _record_method_success(url: str, method: str) -> None:
    method_backoff_cache.pop(_method_key(url, method), None)
    _persist_preflight_cache()


def _record_method_failure(
    url: str,
    method: str,
    base_seconds: int,
    *,
    max_seconds: int = BACKOFF_MAX_SECONDS,
) -> None:
    key = _method_key(url, method)
    entry = method_backoff_cache.setdefault(key, {"failures": 0})
    entry["failures"] = entry.get("failures", 0) + 1
    exponent = min(entry["failures"] - 1, 6)
    backoff_seconds = min(base_seconds * (2**exponent), max_seconds)
    entry["until"] = time.time() + backoff_seconds
    entry["last"] = time.time()
    logging.info(
        "Method backoff for %s (%s): %ds",
        sanitize_url(url),
        method,
        backoff_seconds,
    )
    _persist_preflight_cache()


FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "LiberationSans-Regular.ttf",
]

# User agent templates used when stealth mode is enabled. The actual version is
# filled dynamically based on the installed Chrome version so that outdated
# strings are avoided.
STEALTH_UA_TEMPLATES = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 "
        "Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 "
        "Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 "
        "Safari/537.36"
    ),
]


def random_user_agent():
    """Return a randomized user agent string for stealth mode."""
    chrome_path = get_chrome_path()
    version = get_chrome_version(chrome_path)
    # Pick a nearby version to avoid obvious automation patterns
    major_version = random.randint(max(100, version - 1), version + 1)
    template = random.choice(STEALTH_UA_TEMPLATES)
    return template.format(version=major_version)


def load_font(size):
    """Return a truetype font for overlays."""
    for font_name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# Global flag to track user activity
user_active = False

_driver_local = threading.local()


def _find_cached_chromedriver() -> str | None:
    env_path = os.getenv("CHROMEDRIVER_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    system_path = shutil.which("chromedriver")
    if system_path:
        return system_path
    cache_root = Path("~/.wdm/drivers/chromedriver").expanduser()
    if not cache_root.exists():
        return None
    candidates = [p for p in cache_root.rglob("chromedriver") if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0])


def get_driver(opts):
    driver = getattr(_driver_local, "driver", None)
    if driver is None:
        chrome_path = get_chrome_path()
        # Selenium can launch the wrong browser binary when Chrome/Chromium is
        # installed outside its default expectation. Setting the binary path up
        # front keeps the system driver, Selenium Manager and webdriver-manager
        # all targeting the same executable.
        if (
            chrome_path
            and hasattr(opts, "binary_location")
            and not getattr(opts, "binary_location", None)
        ):
            opts.binary_location = chrome_path

        cached_driver = _find_cached_chromedriver()
        if cached_driver:
            try:
                service = Service(cached_driver)
                driver = webdriver.Chrome(service=service, options=opts)
                _driver_local.driver = driver
                return driver
            except Exception as exc:
                logging.warning(
                    "Failed to launch preferred driver %s: %s",
                    cached_driver,
                    exc,
                )

        if not is_system_online():
            logging.warning("System offline; skipping driver setup")
            return None
        try:
            driver = webdriver.Chrome(options=opts)
            _driver_local.driver = driver
            return driver
        except Exception as exc:
            logging.warning("Failed to launch Selenium Manager driver: %s", exc)
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            _driver_local.driver = driver
            return driver
        except Exception as exc:
            logging.error("Failed to launch driver: %s", exc)
            return None
    return driver


_session = None


def http_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.verify = config.REQUEST_VERIFY_SSL
        _session.headers.update({"user-agent": UA})
        _session.headers.update({"Accept": "*/*"})
        _session.mount("http://", requests.adapters.HTTPAdapter(pool_maxsize=20))
        _session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=20))
    return _session


def _is_valid_png(path: str) -> bool:
    """Return ``True`` if ``path`` points to a valid, readable PNG."""

    try:
        # Other image consumers may enable Pillow's tolerant truncation mode.
        # Verify PNG chunks first so that setting cannot accept a partial frame.
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()  # fully read file to detect truncation
        return True
    except Exception:
        return False


def _sanitize_path(path: str) -> str:
    """Return a normalized absolute path."""
    return os.path.abspath(os.path.normpath(path))


def detect_background_color(image: Image.Image, sample_width: int = 10):
    """Return the most common color found along the image border."""
    arr = np.asarray(image.convert("RGBA"))
    top = arr[:sample_width, :, :].reshape(-1, 4)
    bottom = arr[-sample_width:, :, :].reshape(-1, 4)
    left = arr[:, :sample_width, :].reshape(-1, 4)
    right = arr[:, -sample_width:, :].reshape(-1, 4)
    border = np.concatenate([top, bottom, left, right], axis=0)
    colors, counts = np.unique(border, axis=0, return_counts=True)
    return tuple(int(c) for c in colors[counts.argmax()])


def remove_background(image, background_color=None, threshold=10):
    """Crop the image to remove the background color border.

    Historically Glimpser expanded the detected content bounding box to a
    16:9 aspect ratio. That can re-introduce large uniform borders when the
    page background is the dominant color (common on video players or map
    embeds). We now prefer *cropping in* to 16:9 when the expansion would
    add substantial padding.
    """

    if background_color is None:
        background_color = detect_background_color(image)

    # Find the bounding box of the non-background area
    bbox = find_bounding_box(image, background_color, threshold)

    def _crop_in_to_aspect_ratio(bbox, aspect_ratio=(16, 9)):
        """Return a centered bbox that fits inside `bbox` with the given ratio."""

        left, top, right, bottom = bbox
        w = max(1, int(right - left))
        h = max(1, int(bottom - top))
        target = aspect_ratio[0] / aspect_ratio[1]
        current = w / h
        if abs(current - target) < 1e-6:
            return bbox
        if current > target:
            new_w = int(h * target)
            if new_w < 1:
                return bbox
            pad = (w - new_w) // 2
            return (left + pad, top, left + pad + new_w, bottom)
        new_h = int(w / target)
        if new_h < 1:
            return bbox
        pad = (h - new_h) // 2
        return (left, top + pad, right, top + pad + new_h)

    # Adjust the bounding box to fit a 16:9 aspect ratio (without adding big borders).
    if bbox:
        expanded = adjust_bbox_to_aspect_ratio(bbox, image.size, aspect_ratio=(16, 9))

        # If expanding would add a lot of padding, crop-in instead.
        if expanded and expanded != bbox:
            ex_left, ex_top, ex_right, ex_bottom = expanded
            left, top, right, bottom = bbox
            pad_left = max(0, left - ex_left)
            pad_top = max(0, top - ex_top)
            pad_right = max(0, ex_right - right)
            pad_bottom = max(0, ex_bottom - bottom)
            pad_max = max(pad_left, pad_top, pad_right, pad_bottom)

            # Threshold: >40px or >4% of min dimension tends to be visible "chrome".
            min_dim = max(1, min(image.size))
            if pad_max > 40 or (pad_max / min_dim) > 0.04:
                bbox = _crop_in_to_aspect_ratio(bbox, aspect_ratio=(16, 9))
            else:
                bbox = expanded
        image = image.crop(bbox)

    return image


def find_bounding_box(
    image: Image.Image,
    background_color=(14, 14, 14, 255),
    threshold: int = 10,
):
    """
    Return (left, top, right, bottom) that contains all pixels whose
    per-channel distance from `background_color` > threshold.

    If *every* pixel is background, returns None.
    """
    # RGBA → ndarray(H, W, 4)
    arr = np.asarray(image.convert("RGBA"), dtype=np.int16)

    bg = np.array(background_color, dtype=np.int16)
    # True where *any* channel differs more than threshold
    fg_mask = np.any(np.abs(arr - bg) > threshold, axis=-1)

    if not fg_mask.any():  # all background
        return None

    ys, xs = np.nonzero(fg_mask)
    top, bottom = ys.min(), ys.max()
    left, right = xs.min(), xs.max()

    return int(left), int(top), int(right), int(bottom)


def adjust_bbox_to_aspect_ratio(bbox, image_size, aspect_ratio=(16, 9)):
    """Adjust the bounding box to fit the specified aspect ratio."""
    left, top, right, bottom = bbox
    bbox_width = right - left
    bbox_height = bottom - top
    if bbox_height == 0:
        bbox_height = 1

    bbox_aspect_ratio = bbox_width / bbox_height

    target_aspect_ratio = aspect_ratio[0] / aspect_ratio[1]

    if bbox_aspect_ratio > target_aspect_ratio:
        # The bounding box is too wide, adjust the height
        new_height = bbox_width / target_aspect_ratio
        vertical_padding = (new_height - bbox_height) / 2
        top = max(0, top - vertical_padding)
        bottom = min(image_size[1], bottom + vertical_padding)
    elif bbox_aspect_ratio < target_aspect_ratio:
        # The bounding box is too tall, adjust the width
        new_width = bbox_height * target_aspect_ratio
        horizontal_padding = (new_width - bbox_width) / 2
        left = max(0, left - horizontal_padding)
        right = min(image_size[0], right + horizontal_padding)

    return (int(left), int(top), int(right), int(bottom))


def is_similar_color(color1, color2, threshold):
    """Check if two colors are similar."""
    return all(abs(c1 - c2) <= threshold for c1, c2 in zip(color1, color2))


def is_mostly_blank(
    image: Image.Image,
    threshold: float = 0.98,
    blank_color=(255, 255, 255),
    text_std_threshold: int = 20,
    dark_threshold: int = 10,
    highlight_threshold: int = 40,
    highlight_ratio_threshold: float = 0.0005,
    edge_ratio: float = 0.05,
    edge_threshold: float = 0.02,
    entropy_threshold: float = 2.0,
    chroma_threshold: float = 6.0,
):
    """Heuristically detect blank or uninteresting frames.

    Args:
        image: Image to inspect.
        threshold: Fraction of blank pixels for detection.
        blank_color: RGB color treated as "blank".
        text_std_threshold: Minimum global std-dev to consider text present.
        dark_threshold: Minimum luma value to avoid dark-frame detection.
        highlight_threshold: Per-pixel luma threshold used to detect sparse highlights
            (e.g., streetlights on night cams) so we don't misclassify real content as blank.
        highlight_ratio_threshold: Minimum fraction of pixels above highlight_threshold to
            consider a dark frame as having content.
        edge_ratio: Fractional border to ignore when analyzing content.
        edge_threshold: Minimum edge density to treat as non-blank.
        entropy_threshold: Minimum grayscale entropy to treat as non-blank.
        chroma_threshold: Minimum average chroma to treat as non-blank.

    Returns:
        True if the image is likely blank; otherwise False.
    """
    base = image.convert("RGB")
    max_dim = max(base.size)
    if max_dim > 512:
        scale = 512 / max_dim
        base = base.resize(
            (int(base.size[0] * scale), int(base.size[1] * scale)), Image.LANCZOS
        )
    arr = np.asarray(base, dtype=np.int16)

    if arr.ndim < 2:
        return False

    if 0 < edge_ratio < 0.5:
        h, w, _ = arr.shape
        crop_h = int(h * edge_ratio)
        crop_w = int(w * edge_ratio)
        if crop_h > 0 and crop_w > 0:
            arr = arr[crop_h : h - crop_h, crop_w : w - crop_w]

    # Tiny images often have little variance and can trigger false positives.
    # Skip blank detection entirely for images smaller than 50x50 pixels.
    if arr.shape[0] < 50 or arr.shape[1] < 50:
        return False

    # ---------- 1.  “Mostly blank?”  ----------
    blank = np.array(blank_color, dtype=np.int16)
    blank_px = np.all(np.abs(arr - blank) <= 30, axis=-1).mean()
    if blank_px >= threshold:
        return True

    # ---------- 2.  “Mostly dominant color?”  ----------
    sample = arr.reshape(-1, 3)
    stride = max(1, int(len(sample) / 5000))
    dominant = np.median(sample[::stride], axis=0)
    dominant_px = np.all(np.abs(arr - dominant) <= 12, axis=-1).mean()
    if dominant_px >= threshold:
        foreground_ratio = 1.0 - float(dominant_px)
        dominant_chroma = float(dominant.max() - dominant.min())
        if foreground_ratio < 0.003 or dominant_chroma < chroma_threshold:
            return True

    gray = np.dot(arr, [0.2126, 0.7152, 0.0722])
    gray_uint = np.clip(gray, 0, 255).astype(np.uint8)
    luma = float(gray.mean())
    gray_std = float(gray.std())
    highlight_ratio = float((gray_uint >= highlight_threshold).mean())

    # ---------- 3.  “Edge density?”  ----------
    # Low edge density + low variance/entropy is a strong blank signal.
    edge_v = np.abs(np.diff(gray, axis=0)) > 12
    edge_h = np.abs(np.diff(gray, axis=1)) > 12
    edge_density = (edge_v.mean() + edge_h.mean()) / 2.0

    # ---------- 2.  “Flat image?”  ----------
    # Low global std-dev ≈ little structure / shapes
    # Allow sparse highlights (night cams) to pass through; a nearly-black frame with a
    # few bright pixels can still be meaningful.
    if (
        gray_std < text_std_threshold
        and edge_density < edge_threshold
        and highlight_ratio < highlight_ratio_threshold
    ):
        return True

    # ---------- 3.  “Too dark?”  ----------
    # Use perceptual luma so pure-dark blue isn’t mis-treated
    # Don't classify night scenes as blank if they contain sparse highlights.
    if (
        luma < dark_threshold
        and edge_density < edge_threshold
        and highlight_ratio < highlight_ratio_threshold
    ):
        return True

    # ---------- 4.  “Low entropy + low chroma?” ----------
    hist, _ = np.histogram(gray_uint, bins=64, range=(0, 255))
    probs = hist.astype(np.float64)
    probs = probs / max(probs.sum(), 1.0)
    entropy = -np.sum(probs[probs > 0] * np.log2(probs[probs > 0]))
    chroma = (arr.max(axis=-1) - arr.min(axis=-1)).mean()
    if (
        entropy < entropy_threshold
        and chroma < chroma_threshold
        and edge_density < edge_threshold
        and gray_std < text_std_threshold
    ):
        return True

    return False


def is_sparse_dark_loading_frame(image: Image.Image) -> bool:
    """Detect dark app-loading frames that contain only tiny spinner/UI marks."""

    base = image.convert("RGB")
    max_dim = max(base.size)
    if max_dim > 512:
        scale = 512 / max_dim
        base = base.resize(
            (int(base.size[0] * scale), int(base.size[1] * scale)),
            Image.LANCZOS,
        )

    arr = np.asarray(base, dtype=np.int16)
    if arr.ndim < 2 or arr.shape[0] < 50 or arr.shape[1] < 50:
        return False

    gray = np.dot(arr, [0.2126, 0.7152, 0.0722])
    gray_uint = np.clip(gray, 0, 255).astype(np.uint8)
    mean_luma = float(gray.mean())
    bright_ratio = float((gray_uint >= 80).mean())
    edge_v = np.abs(np.diff(gray, axis=0)) > 12
    edge_h = np.abs(np.diff(gray, axis=1)) > 12
    edge_density = (edge_v.mean() + edge_h.mean()) / 2.0
    hist, _ = np.histogram(gray_uint, bins=64, range=(0, 255))
    probs = hist.astype(np.float64)
    probs = probs / max(probs.sum(), 1.0)
    entropy = -np.sum(probs[probs > 0] * np.log2(probs[probs > 0]))

    return bool(
        mean_luma < 28.0
        and bright_ratio < 0.035
        and edge_density < 0.025
        and entropy < 1.2
    )


def _pixel_luma(pixel: tuple[int, int, int]) -> float:
    r, g, b = pixel
    return (0.299 * r) + (0.587 * g) + (0.114 * b)


def _sample_pixels(
    image: Image.Image,
    box: tuple[int, int, int, int],
    size: tuple[int, int],
) -> list[tuple[int, int, int]]:
    return list(image.crop(box).resize(size).convert("RGB").getdata())


def is_eufy_cellular_reminder_frame(image: Image.Image) -> bool:
    """Detect Eufy's white cellular-data reminder overlay."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 600 or height < 600:
        return False

    dialog = _sample_pixels(
        rgb,
        (
            int(width * 0.25),
            int(height * 0.41),
            int(width * 0.75),
            int(height * 0.58),
        ),
        (120, 48),
    )
    if not dialog:
        return False

    white_ratio = sum(
        1
        for r, g, b in dialog
        if r > 218 and g > 218 and b > 218 and max(r, g, b) - min(r, g, b) < 36
    ) / len(dialog)
    return white_ratio > 0.50


def is_eufy_loading_shell_frame(image: Image.Image) -> bool:
    """Detect Eufy's dark player shell when no camera frame has loaded."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 600 or height < 600:
        return False

    frame = list(rgb.resize((96, 96)).getdata())
    player = _sample_pixels(
        rgb,
        (
            int(width * 0.13),
            int(height * 0.26),
            int(width * 0.87),
            int(height * 0.70),
        ),
        (96, 56),
    )
    if not frame or not player:
        return False

    frame_dark = sum(1 for pixel in frame if max(pixel) < 32) / len(frame)
    player_dark = sum(1 for pixel in player if max(pixel) < 18) / len(player)
    return frame_dark > 0.86 and player_dark > 0.92


def is_eufy_bottom_modal_frame(image: Image.Image) -> bool:
    """Detect a bottom sheet blocking the Eufy camera view."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 600 or height < 600:
        return False

    bottom = _sample_pixels(rgb, (0, int(height * 0.66), width, height), (120, 42))
    if not bottom:
        return False

    white_sheet = sum(
        1
        for r, g, b in bottom
        if r > 232 and g > 232 and b > 232 and max(r, g, b) - min(r, g, b) < 22
    ) / len(bottom)
    dark_sheet = sum(1 for pixel in bottom if _pixel_luma(pixel) < 28) / len(bottom)
    bright_text = sum(1 for pixel in bottom if _pixel_luma(pixel) > 210) / len(bottom)
    return white_sheet >= 0.46 or (dark_sheet >= 0.70 and bright_text >= 0.006)


def is_sparse_dashboard_frame(image: Image.Image) -> bool:
    """Detect sparse but structured dark dashboard frames.

    Hubitat status dashboards can be mostly dark with only a handful of bright
    cards/icons. That looks similar to an app loader to the generic blank-frame
    heuristic, so this accepts sparse frames only when the bright pixels have
    enough two-dimensional structure. A single long loading bar should not pass.
    """

    base = image.convert("RGB")
    max_dim = max(base.size)
    if max_dim > 512:
        scale = 512 / max_dim
        base = base.resize(
            (max(1, int(base.size[0] * scale)), max(1, int(base.size[1] * scale))),
            Image.LANCZOS,
        )

    arr = np.asarray(base, dtype=np.int16)
    if arr.ndim < 2 or arr.shape[0] < 50 or arr.shape[1] < 50:
        return False

    gray = np.dot(arr, [0.2126, 0.7152, 0.0722])
    mean_luma = float(gray.mean())
    if mean_luma > 170.0:
        return False
    mask = gray >= 50
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return False

    h, w = gray.shape[:2]
    x_bins = len(set(np.clip((xs / max(w / 16.0, 1.0)).astype(int), 0, 15)))
    y_bins = len(set(np.clip((ys / max(h / 12.0, 1.0)).astype(int), 0, 11)))
    bbox_w = int(xs.max() - xs.min() + 1)
    bbox_h = int(ys.max() - ys.min() + 1)
    bbox_aspect = bbox_w / max(float(bbox_h), 1.0)
    active_rows = int((mask.sum(axis=1) > 2).sum())
    active_cols = int((mask.sum(axis=0) > 2).sum())

    return bool(
        x_bins >= 3
        and y_bins >= 2
        and active_rows >= 14
        and active_cols >= 24
        and bbox_aspect < 12.0
    )


def is_color_bars_pattern(
    image: Image.Image,
    *,
    min_runs: int = 6,
    max_runs: int = 9,
    min_palette_matches: int = 5,
    max_color_distance: float = 62.0,
    max_region_std: float = 46.0,
    min_saturation: float = 70.0,
) -> bool:
    """Detect SMPTE-style color bar test patterns in captured frames.

    The failure mode we care about is a synthetic feed that produces a small
    number of wide, vertically uniform bars. Real scenes rarely produce that
    many low-variance vertical runs that also match the canonical bar palette.
    """

    base = image.convert("RGB")
    max_dim = max(base.size)
    if max_dim > 480:
        scale = 480 / max_dim
        base = base.resize(
            (max(1, int(base.size[0] * scale)), max(1, int(base.size[1] * scale))),
            Image.LANCZOS,
        )

    arr = np.asarray(base, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[0] < 60 or arr.shape[1] < 120:
        return False

    h, w, _ = arr.shape
    top = int(h * 0.16)
    bottom = int(h * 0.72)
    left = int(w * 0.02)
    right = int(w * 0.98)
    focus = arr[top:bottom, left:right]
    if focus.size == 0:
        return False

    column_rgb = focus.mean(axis=0)
    if column_rgb.shape[0] < 48:
        return False

    smoothed = column_rgb.copy()
    kernel = np.ones(5, dtype=np.float32) / 5.0
    for idx in range(3):
        smoothed[:, idx] = np.convolve(smoothed[:, idx], kernel, mode="same")

    min_run_width = max(8, int(smoothed.shape[0] * 0.05))
    boundaries = (
        np.where(np.linalg.norm(np.diff(smoothed, axis=0), axis=1) > 28.0)[0] + 1
    )

    filtered_boundaries = []
    last_boundary = 0
    for boundary in boundaries:
        if boundary - last_boundary >= min_run_width:
            filtered_boundaries.append(int(boundary))
            last_boundary = int(boundary)

    runs = []
    start = 0
    for boundary in filtered_boundaries:
        if boundary - start >= min_run_width:
            runs.append((start, boundary))
            start = boundary
    if smoothed.shape[0] - start >= min_run_width:
        runs.append((start, smoothed.shape[0]))

    if not (min_runs <= len(runs) <= max_runs):
        return False

    palette = np.asarray(
        [
            (255, 255, 255),
            (255, 255, 0),
            (0, 255, 255),
            (0, 255, 0),
            (255, 0, 255),
            (255, 0, 0),
            (0, 0, 255),
            (0, 0, 0),
        ],
        dtype=np.float32,
    )

    palette_matches = 0
    saturated_runs = 0
    matched_width = 0
    for start, end in runs:
        region = focus[:, start:end, :]
        if region.size == 0:
            continue
        mean_rgb = region.mean(axis=(0, 1))
        region_std = float(region.std(axis=(0, 1)).mean())
        color_distance = float(np.linalg.norm(palette - mean_rgb, axis=1).min())
        saturation = float(mean_rgb.max() - mean_rgb.min())

        if saturation >= min_saturation:
            saturated_runs += 1
        if color_distance <= max_color_distance and region_std <= max_region_std:
            palette_matches += 1
            matched_width += end - start

    matched_width_ratio = matched_width / max(float(focus.shape[1]), 1.0)
    required_matches = max(min_palette_matches, len(runs) - 1)
    return (
        palette_matches >= required_matches
        and saturated_runs >= max(min_runs - 1, 4)
        and matched_width_ratio >= 0.78
    )


def _captured_frame_rejection_reason(image: Image.Image) -> str | None:
    """Return a rejection reason for unusable synthetic capture output."""

    if is_mostly_blank(image):
        return "blank"
    if is_sparse_dark_loading_frame(image):
        return "loading"
    if is_color_bars_pattern(image):
        return "test_pattern"
    return None


def _is_eufy_snapshot_proxy_url(url: str | None) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.path.rstrip("/") == "/integrations/eufy/snapshot"


def _is_direct_camera_snapshot_url(source_url: str | None) -> bool:
    """Identify camera snapshots whose compressed size changes with the scene."""
    parsed = urlparse(str(source_url or ""))
    return parsed.scheme in {"http", "https"} and bool(
        re.fullmatch(
            r"/ISAPI/Streaming/channels/\d+/picture/?", parsed.path, re.IGNORECASE
        )
    )


def _is_low_light_camera_frame(image: Image.Image, source_url: str | None) -> bool:
    """Recognize darkness from a direct camera snapshot, never a website loader.

    A covered lens or unlit room is still the camera's current output. Show that
    output with a low-light label instead of silently retaining a daylight image.
    """

    if not _is_direct_camera_snapshot_url(source_url):
        return False
    if min(image.size) < 200:
        return False
    sample = image.convert("L")
    sample.thumbnail((320, 240))
    pixels = np.asarray(sample)
    h, w = pixels.shape
    center = pixels[h // 5 : 4 * h // 5, w // 5 : 4 * w // 5]
    return bool(float(center.mean()) < 12 and np.percentile(center, 95) < 24)


def _downloaded_still_rejection_reason(
    image: Image.Image,
    source_url: str | None,
) -> str | None:
    """Return a rejection reason for source-specific still-image artifacts."""

    if _is_eufy_snapshot_proxy_url(source_url):
        if is_eufy_cellular_reminder_frame(image):
            return "cellular_reminder"
        if is_eufy_loading_shell_frame(image):
            return "loading_shell"
        if is_eufy_bottom_modal_frame(image):
            return "bottom_modal"
    reason = _captured_frame_rejection_reason(image)
    if reason == "blank" and _is_low_light_camera_frame(image, source_url):
        return None
    return reason


def run_cmd(cmd, timeout):
    """Run a command and return its output.

    Args:
        cmd (Sequence[str]): Command to execute.
        timeout (int): Timeout in seconds.

    Returns:
        bytes: Captured standard output.

    Raises:
        RuntimeError: If the command fails or times out.
    """

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()  # SIGKILL
        out, err = proc.communicate()
        raise RuntimeError(f"timeout: {' '.join(cmd)}")
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        proc.wait(timeout=5)
    if proc.returncode:
        raise RuntimeError(err.decode()[:300])
    return out


def add_timestamp(
    image_path,
    name="unknown",
    invert=False,
    show_name=True,
    mode: str | None = None,
):
    """Overlay name and timestamp onto an image.

    Args:
        image_path (str): Path to the PNG file.
        name (str): Label to render on the image.
        invert (bool): Invert text for dark images.
        show_name (bool): Whether to render the camera name.
        mode (str | None): ``clean``, ``compact`` or ``debug``. Defaults to
            ``VISUAL_TIMESTAMP_MODE``.
    """

    timestamp_mode = _normalize_visual_timestamp_mode(mode)
    if os.path.exists(image_path):
        with Image.open(
            image_path
        ) as image:  # consider unlinking if this fails to open
            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            try:
                image = image.convert("RGB")
            except Exception as e:
                # for debugging only, otherwise unlink the file
                if DEBUG:
                    os.rename(image_path, image_path.replace(".png", ".broken"))
                else:
                    # unlink the offending image
                    os.unlink(image_path)
                # print(" warning : image load issue:", image_path, e)
                logging.error(f"Error saving image: {image_path} {e}")
                return

            draw = ImageDraw.Draw(image)
            # If the image has the "invert" flag, then invert colors for readability
            if invert:
                image = ImageOps.invert(image)

            if timestamp_mode == "clean":
                image.save(
                    image_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL
                )
                return

            # Define the timestamp format

            zone = tz.gettz(TZ) or tz.UTC  # fall back if the name is invalid
            local_time = datetime.datetime.now(zone)
            tz_name = local_time.tzname() or ""
            if timestamp_mode == "compact":
                timestamp = local_time.strftime("%m-%d %H:%M")
            else:
                timestamp = local_time.strftime("%Y-%m-%d %H:%M:%S")
            if tz_name:
                timestamp = f"{timestamp} {tz_name}"

            utc_time = datetime.datetime.utcnow()
            utc_timestamp = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")

            max_height = min(image.height, image.width * 9 // 16)
            font_ratio = 0.035 if not show_name else 0.05
            font_size = int(max_height * font_ratio)
            if font_size < 5:  # ignore tiny images
                return

            top_offset = (image.height - max_height) / 2

            # Use the helper to load fonts. The small font is half-sized.
            font = load_font(font_size)
            font_small = load_font(int(max(5, font_size / 2)))

            padding = 6

            # Render the name in the upper-left corner unless the capture already
            # contains dense dashboard labels that would be obscured.
            if show_name:
                x = padding
                y = int(padding + top_offset)
                bbox = draw.textbbox((x, y), name, font=font, stroke_width=1)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                background = Image.new(
                    "RGBA",
                    (text_w + padding * 2, text_h + padding * 2),
                    (0, 0, 0, 128),
                )
                image.paste(background, (x - padding, y - padding), background)
                draw.text(
                    (x, y),
                    name,
                    font=font,
                    fill=(255, 255, 255, 255),
                    stroke_width=1,
                    stroke_fill=(0, 0, 0, 255),
                )

            # Timestamp in the lower-right corner
            text_w = draw.textbbox((0, 0), timestamp, font=font, stroke_width=1)[2]
            x = image.width - text_w - padding
            y = int(image.height - top_offset - font_size * 2)
            bbox = draw.textbbox((x, y), timestamp, font=font, stroke_width=1)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            background = Image.new(
                "RGBA",
                (text_w + padding * 2, text_h + padding * 2),
                (0, 0, 0, 128),
            )
            image.paste(background, (bbox[0] - padding, bbox[1] - padding), background)

            draw.text(
                (x, y),
                timestamp,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
            )

            if timestamp_mode == "debug" and utc_timestamp != timestamp:
                tz_bbox = draw.textbbox(
                    (0, 0), utc_timestamp, font=font_small, stroke_width=1
                )
                text_w = tz_bbox[2] - tz_bbox[0]
                text_h = tz_bbox[3] - tz_bbox[1]
                background = Image.new(
                    "RGBA",
                    (text_w + padding * 2, text_h + padding * 2),
                    (0, 0, 0, 128),
                )
                tz_x = x
                tz_y = y + font_size + padding
                image.paste(
                    background,
                    (tz_x - padding, tz_y - padding),
                    background,
                )
                draw.text(
                    (tz_x, tz_y),
                    utc_timestamp,
                    font=font_small,
                    fill=(255, 255, 255, 255),
                    stroke_width=1,
                    stroke_fill=(0, 0, 0, 255),
                )

            # Save the image
            image.save(image_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)

        if timestamp_mode != "debug":
            return

        try:
            from .qrcode_overlay import add_micro_barcode

            add_micro_barcode(image_path, name)
        except Exception as e:  # pragma: no cover - overlay failures are non-critical
            logging.debug(f"Micro barcode overlay failed: {e}")


def create_placeholder(image_path, name="unknown"):
    """Generate a simple placeholder image with a timestamp."""
    img = Image.new("RGB", (640, 360), color="black")
    draw = ImageDraw.Draw(img)
    font = load_font(20)
    zone = tz.gettz(TZ) or tz.UTC
    timestamp = datetime.datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S")
    text = f"{name}\n{timestamp}"
    draw.multiline_text((10, 10), text, fill=(255, 255, 255), font=font)
    img.save(image_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)


def download_image(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    dark=False,
    stealth=False,
    proxy=None,
    username=None,
    password=None,
    stabilize_mode="off",
    read_timeout=None,
    source_identity=None,
):
    """Attempt to download an image directly from the URL and convert it to PNG format.

    Args:
        url (str): Image URL.
        output_path (str): Where to save the PNG.
        timeout (int): Timeout in seconds.
        name (str): Friendly name for logging.
        invert (bool): If True, invert timestamp colors.
        dark (bool): Apply dark mode.
        stealth (bool): Use stealth user agent.
        proxy (str, optional): Proxy to use for the HTTP request.
        source_identity (str, optional): Configured source before proxy resolution.
    """

    from app.utils.source_freshness import read_evidence, record_source

    proxy = validate_proxy(proxy)
    clean_url = sanitize_url(url)
    output_path = _sanitize_path(output_path)

    # Ideally the timeout should be pretty high for normal images because some
    # camera stills are large. Specific flaky sources can pass a smaller
    # read_timeout to avoid tying up scheduler workers during upstream hangs.
    timeout = max(timeout, 10)
    read_timeout = timeout * 3 if read_timeout is None else max(float(read_timeout), 1)

    response = None

    try:
        lua = UA
        if stealth:
            lua = random_user_agent()
        headers = {"user-agent": lua}
        proxies = {"http": proxy, "https": proxy} if proxy else None
        static_chart_dark = _static_chart_dark_mode_enabled(
            name,
            None,
            dark,
            source_url=url,
        )

        auth = get_preferred_auth(url, username, password)
        cached = get_cached_status_code(url)
        if cached in {401, 403, 404, 410, 429}:
            # A cached unauthenticated 401 must not poison camera templates that
            # have stored credentials; Hikvision/NVR still endpoints commonly
            # advertise auth this way before succeeding with Digest/Basic auth.
            if cached != 401 or auth is None:
                logging.debug(f"Skipping {clean_url} due to cached status {cached}")
                return False

        request_kwargs = dict(
            stream=True,
            timeout=(timeout, read_timeout),
            verify=config.REQUEST_VERIFY_SSL,
            headers=headers,
            auth=auth,
        )
        if proxies:
            request_kwargs["proxies"] = proxies

        response = http_session().get(url, **request_kwargs)
        if response.status_code == 401:
            scheme, realm = _parse_www_authenticate(
                response.headers.get("WWW-Authenticate", "")
            )
            if scheme:
                _set_auth_scheme(url, scheme, realm)
            if auth is None:
                _set_auth_hint(url)
                response.close()
                return False
            auth = (
                get_digest_auth(url, username, password) if scheme == "digest" else auth
            )
            request_kwargs = dict(
                stream=True,
                timeout=(timeout, read_timeout),
                verify=config.REQUEST_VERIFY_SSL,
                headers=headers,
                auth=auth,
            )
            if proxies:
                request_kwargs["proxies"] = proxies

            # The streamed 401 owns a connection until explicitly closed.
            # Release it before opening the authenticated retry.
            response.close()
            response = None
            response = http_session().get(url, **request_kwargs)

        status = response.status_code
        # Some hosts return transient 403/503 based on User-Agent heuristics.
        # Retry once with a very plain UA before caching the failure.
        if status in {403, 503} and headers.get("user-agent") == UA:
            try:
                response.close()
            except Exception:
                pass
            alt_headers = dict(headers)
            alt_headers["user-agent"] = "Mozilla/5.0"
            request_kwargs["headers"] = alt_headers
            response = http_session().get(url, **request_kwargs)
            status = response.status_code

        if status == 429:
            record_rate_limit(url, response)
            return False
        set_cached_status_code(url, status)

        if status == 200:
            eufy_snapshot = _is_eufy_snapshot_proxy_url(url)
            hash_limit = (
                max(IMAGE_HASH_MAX_BYTES, 16 * 1024 * 1024)
                if eufy_snapshot
                else IMAGE_HASH_MAX_BYTES
            )
            if response.content and len(response.content) <= hash_limit:
                digest = hashlib.sha256(response.content).hexdigest()
                evidence = read_evidence(name)
                logical_source = source_identity or url
                accepted_same = (
                    evidence.get("digest") == digest
                    and evidence.get("identity")
                    == hashlib.sha256(str(logical_source).encode()).hexdigest()
                    and _has_existing_screenshot(name)
                )
                if accepted_same and (eufy_snapshot or digest == _get_image_hash(url)):
                    record_source(
                        name,
                        logical_source,
                        digest=digest,
                        modified=response.headers.get("Last-Modified", ""),
                    )
                    if not static_chart_dark:
                        # A successful fetch of identical bytes is a source check,
                        # not a newly saved image. Keep the existing capture time.
                        response.close()
                        return CAPTURE_SOURCE_UNCHANGED
                    logging.debug(
                        "[%s] Reprocessing unchanged static chart for dark mode", name
                    )
                _set_image_hash(url, digest)
            # Open the image directly from the response bytes
            image = Image.open(io.BytesIO(response.content))
            response.close()

            low_light_frame = _is_low_light_camera_frame(image, url)
            reject_reason = _downloaded_still_rejection_reason(image, url)
            if reject_reason is not None:
                logging.warning(
                    "[%s] Rejecting downloaded still due to %s frame: %s",
                    name,
                    reject_reason,
                    clean_url,
                )
                if _has_existing_screenshot(name):
                    logging.warning(
                        "[%s] Keeping previous screenshot after %s frame rejection",
                        name,
                        reject_reason,
                    )
                    return CAPTURE_STALE_PREVIOUS
                record_preflight_backoff(
                    url,
                    f"{reject_reason}_capture",
                    PREFLIGHT_BACKOFF_BROWSER_FAIL,
                )
                return False

            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            image = _postprocess_still_image(
                image,
                output_path,
                name,
                dark=dark,
                stabilize_mode=stabilize_mode,
                remove_bg=not low_light_frame,
            )
            reject_reason = _downloaded_still_rejection_reason(image, url)
            if low_light_frame and reject_reason == "blank":
                reject_reason = None
            if reject_reason is not None and not static_chart_dark:
                logging.warning(
                    "[%s] Rejecting processed still due to %s frame: %s",
                    name,
                    reject_reason,
                    clean_url,
                )
                if _has_existing_screenshot(name):
                    logging.warning(
                        "[%s] Keeping previous screenshot after %s frame rejection",
                        name,
                        reject_reason,
                    )
                    return CAPTURE_STALE_PREVIOUS
                record_preflight_backoff(
                    url,
                    f"{reject_reason}_postprocess",
                    PREFLIGHT_BACKOFF_BROWSER_FAIL,
                )
                return False
            if reject_reason is not None:
                logging.debug(
                    "[%s] Keeping allowlisted dark static chart despite %s heuristic",
                    name,
                    reject_reason,
                )

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            tmp_path = output_path + ".tmp"

            # Save to a temporary file first so readers don't see partial data
            image.save(tmp_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)
            if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
                add_timestamp(tmp_path, name=name, invert=invert)
                os.replace(tmp_path, output_path)
                record_source(
                    name,
                    source_identity or url,
                    digest=hashlib.sha256(response.content).hexdigest(),
                    modified=response.headers.get("Last-Modified", ""),
                    capture_file=os.path.basename(output_path),
                    frame_condition="low_light" if low_light_frame else "",
                )
                return True
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        else:
            if status in {403, 404, 410}:
                _set_http_error(url, status)
            response.close()
            logging.warning(
                f"Error downloading image: HTTP status code {status} {clean_url}"
            )
            cas_error(url)
    except Exception as e:
        logging.warning(f"Error downloading image: {e} {clean_url} {timeout}")
        set_cached_status_code(url, 0)
        cas_error(url)
    finally:
        if response is not None:
            response.close()  # Ensure the connection is closed

    return False


def download_pdf(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    dark=False,
    stealth=False,
    username=None,
    password=None,
    stabilize_mode="off",
):
    """
    Attempt to download the first page of a PDF from the URL and convert it to PNG format.
    """
    lsuccess = False

    clean_url = sanitize_url(url)
    output_path = _sanitize_path(output_path)

    cached = get_cached_status_code(url)
    if cached is not None and cached != 200:
        logging.debug(
            f"Skipping PDF download for {clean_url} due to cached status {cached}"
        )
        return False

    timeout = max(timeout, 10)

    response = None
    try:
        # Download the PDF file
        lua = UA
        if stealth:
            lua = random_user_agent()

        headers = {"user-agent": lua}
        auth = get_preferred_auth(url, username, password)

        response = http_session().get(
            url,
            stream=True,
            timeout=timeout,
            verify=config.REQUEST_VERIFY_SSL,
            headers=headers,
            auth=auth,
            allow_redirects=True,
        )

        # Possibly re-try with DigestAuth if 401
        if response.status_code == 401:
            scheme, realm = _parse_www_authenticate(
                response.headers.get("WWW-Authenticate", "")
            )
            if scheme:
                _set_auth_scheme(url, scheme, realm)
            if auth is None:
                _set_auth_hint(url)
                return False
            auth = (
                get_digest_auth(url, username, password) if scheme == "digest" else auth
            )
            response.close()
            response = None
            response = http_session().get(
                url,
                stream=True,
                timeout=timeout,
                verify=config.REQUEST_VERIFY_SSL,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )
        if response.status_code == 429:
            record_rate_limit(url, response)
            return False
        set_cached_status_code(url, response.status_code)

        if response.status_code != 200:
            logging.warning(f"Error downloading PDF: HTTP {response.status_code}")
            if response.status_code in {403, 404, 410}:
                _set_http_error(url, response.status_code)
            cas_error(url)
            return False

        # Convert the first page to an image directly from the response bytes
        document_bytes = response.content
        response.close()
        response = None
        pages = convert_from_bytes(document_bytes, first_page=1, last_page=1)
        if not pages:
            logging.error("Error converting PDF to image: No pages found")
            return False

        reject_reason = _captured_frame_rejection_reason(pages[0])
        if reject_reason is not None:
            logging.warning(
                "[%s] Rejecting downloaded PDF preview due to %s frame: %s",
                name,
                reject_reason,
                clean_url,
            )
            record_preflight_backoff(
                url,
                f"{reject_reason}_capture",
                PREFLIGHT_BACKOFF_BROWSER_FAIL,
            )
            return False

        image = _postprocess_still_image(
            pages[0],
            output_path,
            name,
            dark=dark,
            stabilize_mode=stabilize_mode,
        )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tmp_path = output_path + ".tmp"
        image.save(tmp_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)

        if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
            add_timestamp(tmp_path, name=name, invert=invert)
            os.replace(tmp_path, output_path)
            logging.debug(f"Successfully saved PDF page to {output_path}")
            lsuccess = True
        elif os.path.exists(tmp_path):
            os.remove(tmp_path)
        return lsuccess

    except Exception as e:
        logging.warning(f"Error downloading PDF: {e}")
        set_cached_status_code(url, 0)
        cas_error(url)
        return False
    finally:
        if response is not None:
            response.close()


def is_enhanced(url):
    """Return True if ``yt_dlp`` has a specialized extractor for the URL."""
    try:
        extractors = youtube_dl.extractor.list_extractors()
    except Exception as e:  # pragma: no cover - defensive
        logging.warning("yt_dlp extractor check failed: %s", e)
        return False
    for extractor in extractors:
        if extractor.suitable(url) and extractor.IE_NAME != "generic":
            return True
    return False


def get_arp_output(ip_address, timeout):
    if platform.system() == "Windows":
        command = ["arp", "-a", ip_address]
    else:
        command = ["ip", "neigh", "show", ip_address]
    try:
        return subprocess.check_output(
            command, stderr=subprocess.STDOUT, timeout=timeout
        )
    except FileNotFoundError:
        return b""


def is_private_ip(ip_address):
    return ipaddress.ip_address(ip_address).is_private


def _reachability_key(address: str, port: int | None) -> str:
    return f"{address.lower()}:{port or 0}"


def _get_reachability_cached(address: str, port: int | None) -> bool | None:
    key = _reachability_key(address, port)
    entry = reachability_cache.get(key)
    if not entry:
        return None
    if entry.get("until", 0) <= time.time():
        return None
    return entry.get("ok")


def _set_reachability_cached(
    address: str, port: int | None, ok: bool, ttl: int
) -> None:
    key = _reachability_key(address, port)
    reachability_cache[key] = {
        "ok": ok,
        "until": time.time() + ttl,
        "last": time.time(),
    }
    _persist_preflight_cache()


def _get_dns_resolve_cached(hostname: str, port: int | None) -> str | None:
    key = f"{hostname.lower()}:{port or 0}"
    cached = dns_resolve_cache.get(key)
    if (
        cached
        and dns_resolve_cache_time.get(key, 0) > time.time() - PREFLIGHT_DNS_RESOLVE_TTL
    ):
        return cached
    return None


def _set_dns_resolve_cached(hostname: str, port: int | None, ip: str) -> None:
    key = f"{hostname.lower()}:{port or 0}"
    dns_resolve_cache[key] = ip
    dns_resolve_cache_time[key] = time.time()
    _persist_preflight_cache()


def _renderer_healthy(renderer: str) -> bool:
    entry = throttle_cache.get(f"renderer:{renderer}")
    if not entry:
        return True
    return entry.get("timeout", 0) <= time.time()


def _record_renderer_failure(renderer: str, reason: str) -> None:
    entry = throttle_cache.setdefault(f"renderer:{renderer}", {"errors": 0})
    now = time.time()
    already_backing_off = entry.get("timeout", 0) > now
    prev_reason = entry.get("reason")
    entry["errors"] = entry.get("errors", 0) + 1
    entry["reason"] = reason
    entry["timeout"] = now + PREFLIGHT_RENDERER_FAIL_TTL
    if already_backing_off and prev_reason == reason:
        return
    logging.warning(
        "Renderer backoff for %s (%s): %ds",
        renderer,
        reason,
        PREFLIGHT_RENDERER_FAIL_TTL,
    )


def _clear_renderer_failure(renderer: str) -> None:
    throttle_cache.pop(f"renderer:{renderer}", None)


def is_address_reachable(address, port=80, timeout=5):
    if port is None:
        port = 80

    timeout = max(float(timeout), 0.05)

    cached = _get_reachability_cached(address, port)
    if cached is not None:
        return cached

    try:
        try:
            ipaddress.ip_address(address)
            ip_address = address
        except ValueError:
            cached_ip = _get_dns_resolve_cached(address, port)
            if cached_ip:
                ip_address = cached_ip
            else:
                # Resolve the domain name to an IP address
                ip_address = socket.gethostbyname(address)
                _set_dns_resolve_cached(address, port, ip_address)
        # print(f"{address} resolved to {ip_address}")
    except Exception:
        if address in ("google.com", "www.google.com"):
            return True
        _set_reachability_cached(address, port, False, PREFLIGHT_REACHABILITY_BACKOFF)
        return False

    # DNS resolution is separate; all TCP source-address attempts share the
    # caller's budget instead of multiplying it by the interface count.
    deadline = time.monotonic() + timeout

    try:

        def _attempt_connect(src_ip: str | None) -> int:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return errno.ETIMEDOUT
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(remaining)
                if src_ip:
                    sock.bind((src_ip, 0))
                return sock.connect_ex((ip_address, port))
            finally:
                sock.close()

        # Attempt using the default source selection first.
        result = _attempt_connect(None)

        # Some multi-homed hosts have multiple private IPv4 addresses (VLANs,
        # secondary IPs, etc). The kernel may choose a "wrong" source address
        # for certain routes, causing false "unreachable" results. If the first
        # attempt fails, retry with explicit binds to each local IPv4 address.
        if result != 0 and is_private_ip(ip_address) and time.monotonic() < deadline:
            candidates: list[str] = []
            try:
                for addrs in psutil.net_if_addrs().values():
                    for addr in addrs:
                        if addr.family != socket.AF_INET:
                            continue
                        src = addr.address
                        try:
                            ip_obj = ipaddress.ip_address(src)
                        except ValueError:
                            continue
                        if ip_obj.is_loopback or ip_obj.is_link_local:
                            continue
                        if not ip_obj.is_private:
                            continue
                        if src not in candidates:
                            candidates.append(src)
            except Exception:
                candidates = []

            for src in candidates:
                try:
                    if _attempt_connect(src) == 0:
                        result = 0
                        break
                except Exception:
                    continue

        if result == 0:
            # print(f"Successfully connected to {ip_address} on port {port}")
            # print(f"Failed to connect to {ip_address} on port {port}")

            _set_reachability_cached(address, port, True, PREFLIGHT_REACHABILITY_TTL)
            return True
        if address in ("google.com", "www.google.com"):
            return True
        _set_reachability_cached(address, port, False, PREFLIGHT_REACHABILITY_BACKOFF)
        return False
    except Exception as e:
        logging.warning(f"Socket error: {e}")
        if address in ("google.com", "www.google.com"):
            return True
        _set_reachability_cached(address, port, False, PREFLIGHT_REACHABILITY_BACKOFF)

    return False


def parse_url(url):
    """Return the domain and port extracted from *url*.

    ``urllib.parse.urlparse`` treats strings without a scheme oddly.  For
    example ``"example.com:8080/path"`` is parsed with ``"example.com"`` as the
    *scheme* rather than the hostname.  To handle such URLs we prefix ``"//"`` so
    they are interpreted as network locations.
    """

    # Handle URLs missing a scheme like ``example.com:8080/path`` by prefixing
    # ``//`` which causes ``urlparse`` to parse the hostname and port correctly.
    if "://" not in url:
        parsed_url = urlparse("//" + url)
    else:
        parsed_url = urlparse(url)

    domain = parsed_url.hostname
    if parsed_url.scheme == "" and domain is None:
        domain = re.sub(r"\/.+?$", "", parsed_url.path)

    port = parsed_url.port
    # If the port is None and the scheme is specified, infer the default port.
    if port is None:
        if parsed_url.scheme == "http":
            port = 80
        elif parsed_url.scheme == "https":
            port = 443
        elif parsed_url.scheme == "rtsp":
            port = 554
        elif parsed_url.scheme == "rtsps":
            # Google SDM GenerateRtspStream returns `rtsps://...`.
            port = 443
        elif parsed_url.scheme == "rtmp":
            port = 1935
        # Add more schemes and their default ports if necessary.

    return domain, port


def _is_private_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _is_probably_local_hostname(hostname: str | None) -> bool:
    """Return ``True`` for hostnames that are likely LAN-only names."""

    if not hostname:
        return False
    host = hostname.strip().lower().rstrip(".")
    if host in {"localhost"}:
        return True
    if "." not in host:
        return True
    return host.endswith((".local", ".lan", ".home", ".arpa"))


def _is_lan_target(hostname: str | None) -> bool:
    """Return ``True`` when *hostname* points to likely LAN/private target."""

    return _is_private_host(hostname) or _is_probably_local_hostname(hostname)


def _danger_chrome_available() -> bool:
    try:
        from .chrome_utils import is_chrome_debug_port_open
    except Exception:
        return False
    return is_chrome_debug_port_open("127.0.0.1", config.DANGER_PORT)


def _danger_session_status() -> dict | None:
    if not _danger_chrome_available():
        return None
    try:
        version = requests.get(
            f"http://127.0.0.1:{config.DANGER_PORT}/json/version",
            timeout=1,
        ).json()
        targets = requests.get(
            f"http://127.0.0.1:{config.DANGER_PORT}/json/list",
            timeout=1,
        ).json()
    except Exception:
        return None
    target_count = len(targets) if isinstance(targets, list) else None
    return {
        "browser": version.get("Browser"),
        "ws": version.get("webSocketDebuggerUrl"),
        "target_count": target_count,
    }


def _maybe_log_danger_session(status: dict, clean_url: str) -> None:
    key = "danger_session"
    entry = danger_session_cache.setdefault(key, {})
    fingerprint = f"{status.get('browser', '')}|{status.get('ws', '')}"
    target_count = status.get("target_count")
    if fingerprint and entry.get("fingerprint") != fingerprint:
        entry["fingerprint"] = fingerprint
        entry["last_seen"] = time.time()
        logging.info(
            "Danger session changed for %s (%s)",
            clean_url,
            status.get("browser") or "unknown",
        )
    if target_count is not None and entry.get("target_count") != target_count:
        entry["target_count"] = target_count
        logging.info(
            "Danger session targets for %s: %s",
            clean_url,
            target_count,
        )
    _persist_preflight_cache()


def _danger_fallback_entry(url: str) -> dict:
    return danger_fallback_cache.setdefault(
        url,
        {
            "failures": [],
            "force_until": 0,
            "backoff_until": 0,
            "last_log": 0,
        },
    )


def _danger_fallback_active(url: str) -> bool:
    if DANGER_FALLBACK_THRESHOLD <= 0:
        return False
    entry = danger_fallback_cache.get(url)
    if not entry:
        return False
    now = time.time()
    if entry.get("force_until", 0) <= now:
        return False
    if entry.get("backoff_until", 0) > now:
        return False
    return True


def _record_danger_fallback_backoff(url: str, clean_url: str, reason: str) -> None:
    now = time.time()
    entry = _danger_fallback_entry(url)
    entry["backoff_until"] = max(
        entry.get("backoff_until", 0), now + DANGER_FALLBACK_BACKOFF_SECONDS
    )
    entry["last_reason"] = reason
    if now - entry.get("last_log", 0) > DANGER_FALLBACK_LOG_THROTTLE:
        entry["last_log"] = now
        if reason == "danger_disabled":
            logging.warning(
                "Danger fallback requested for %s, but DANGER_MODE is disabled. "
                "Enable it in Settings > Danger or set DANGER_MODE=True.",
                clean_url,
            )
        elif reason == "danger_unavailable":
            logging.warning(
                "Danger fallback unavailable for %s; Chrome debug port %s is closed. "
                "Start Chrome with --remote-debugging-port=%s.",
                clean_url,
                config.DANGER_PORT,
                config.DANGER_PORT,
            )
        else:
            logging.warning(
                "Danger fallback paused for %s (%s): %ds",
                clean_url,
                reason,
                DANGER_FALLBACK_BACKOFF_SECONDS,
            )
    _persist_preflight_cache()


def _record_browser_failure_for_danger(url: str, reason: str) -> None:
    if DANGER_FALLBACK_THRESHOLD <= 0:
        return
    now = time.time()
    entry = _danger_fallback_entry(url)
    failures = [
        stamp
        for stamp in entry.get("failures", [])
        if stamp >= now - DANGER_FALLBACK_WINDOW_SECONDS
    ]
    failures.append(now)
    entry["failures"] = failures
    entry["last_reason"] = reason
    if len(failures) >= DANGER_FALLBACK_THRESHOLD:
        entry["force_until"] = max(
            entry.get("force_until", 0), now + DANGER_FALLBACK_FORCE_SECONDS
        )
        if now - entry.get("last_log", 0) > DANGER_FALLBACK_LOG_THROTTLE:
            entry["last_log"] = now
            logging.info(
                "Danger fallback armed for %s after %d browser failures in %ds",
                sanitize_url(url),
                len(failures),
                DANGER_FALLBACK_WINDOW_SECONDS,
            )
    _persist_preflight_cache()


def _clear_danger_fallback(url: str) -> None:
    if danger_fallback_cache.pop(url, None) is not None:
        _persist_preflight_cache()


def _danger_fallback_ready(url: str, clean_url: str) -> bool:
    if config.get_setting("DANGER_MODE", "True") != "True":
        _record_danger_fallback_backoff(url, clean_url, "danger_disabled")
        return False
    if not _danger_chrome_available():
        _record_danger_fallback_backoff(url, clean_url, "danger_unavailable")
        return False
    status = _danger_session_status()
    if status:
        _maybe_log_danger_session(status, clean_url)
    return True


def cas_error(url):
    entry = throttle_cache.setdefault(url, {"errors": 0, "first": time.time()})

    if entry.get("last", 0) > time.time() - 60 * 5:
        entry["errors"] += 1
    else:
        entry["errors"] = 1
        entry["first"] = time.time()
    entry["last"] = time.time()

    if entry["errors"] > 2:
        logging.error(
            f"Could not reach host: {sanitize_url(url)} {entry['errors']} times"
        )
        entry["timeout"] = time.time() + 60 * 60  # 1 hour timeout


def _record_rtsp_preflight_failure(url: str, reason: str) -> bool:
    entry = throttle_cache.setdefault(url, {"errors": 0, "first": time.time()})
    now = time.time()
    first = entry.get("rtsp_preflight_first", now)
    if now - first > RTSP_PREFLIGHT_FAIL_WINDOW_SECONDS:
        entry["rtsp_preflight_first"] = now
        entry["rtsp_preflight_failures"] = 1
    else:
        entry["rtsp_preflight_failures"] = entry.get("rtsp_preflight_failures", 0) + 1
    failures = entry["rtsp_preflight_failures"]
    if failures >= RTSP_PREFLIGHT_FAIL_THRESHOLD:
        record_preflight_backoff(
            url,
            f"rtsp_preflight_{reason}",
            RTSP_PREFLIGHT_BACKOFF_SECONDS,
        )
        return True
    return False


def record_rate_limit(url: str, response, default_seconds: int = 1800) -> None:
    """Record a rate limit response and set a per-URL backoff timeout."""

    _record_retry_after(url, response, default_seconds, reason="rate_limit")


def _record_retry_after(
    url: str, response, default_seconds: int, *, reason: str
) -> None:
    retry_after = response.headers.get("Retry-After")
    backoff_seconds = default_seconds
    if retry_after:
        try:
            backoff_seconds = max(int(retry_after), 0)
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(retry_after)
                if parsed is not None:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=datetime.UTC)
                    delta = (
                        parsed - datetime.datetime.now(datetime.UTC)
                    ).total_seconds()
                    backoff_seconds = max(int(delta), 0)
            except Exception:
                backoff_seconds = default_seconds

    entry = throttle_cache.setdefault(url, {"errors": 0, "first": time.time()})
    entry["timeout"] = time.time() + backoff_seconds
    entry["last"] = time.time()
    entry["reason"] = reason
    logging.warning(
        "HTTP retry-after for %s (%s); backing off for %ds",
        sanitize_url(url),
        reason,
        backoff_seconds,
    )


def record_preflight_backoff(url: str, reason: str, backoff_seconds: int) -> None:
    stable = stable_key_for_resolved_rtsp(str(url or ""))
    if stable:
        url = stable

    """Set a short backoff window after a preflight or capture failure."""

    entry = throttle_cache.setdefault(url, {"errors": 0, "first": time.time()})
    entry["last"] = time.time()
    entry["reason"] = reason
    entry["timeout"] = max(entry.get("timeout", 0), time.time() + backoff_seconds)
    logging.info(
        "Preflight backoff for %s (%s): %ds",
        sanitize_url(url),
        reason,
        backoff_seconds,
    )


def _weatherbug_latest_sort_key(image_url: str) -> str:
    """Return a sortable key for WeatherBug dated still URLs."""

    match = re.search(
        r"/(\d{4})/(\d{2})/(\d{2})/(\d{12})_l\.jpg(?:\?|$)",
        image_url,
    )
    if match:
        return "".join(match.groups())
    return image_url


def _is_weatherbug_camera_url(url: str | None) -> bool:
    """Return True when *url* is a WeatherBug camera page."""

    parsed_page = urlparse(str(url or ""))
    return bool(
        re.search(
            r"^(www\.)?weatherbug\.com$",
            parsed_page.netloc,
            flags=re.I,
        )
        and parsed_page.path.lower().startswith("/weather-camera")
    )


def _is_limnotech_resized_image_url(url: str | None) -> bool:
    """Return True for LimnoTech Zenphoto image-resizer URLs."""

    parsed = urlparse(str(url or ""))
    return bool(
        url_matches_host(str(url or ""), "limnotechdata.com")
        and parsed.path.lower().endswith("/stations/zp-core/i.php")
        and parse_qs(parsed.query).get("i", [""])[0].lower().endswith(".jpg")
    )


def _weatherbug_extract_latest_image(page_url: str, timeout: int = 30) -> str | None:
    """Extract the current camera still from a WeatherBug camera page."""

    parsed_page = urlparse(page_url)
    if not _is_weatherbug_camera_url(page_url):
        return None
    path_parts = [part.strip() for part in parsed_page.path.split("/") if part.strip()]
    if not path_parts or path_parts[0].lower() != "weather-camera":
        return None
    cam_id = (parse_qs(parsed_page.query).get("cam") or [""])[0].strip().upper()
    if not cam_id and len(path_parts) >= 2:
        cam_id = path_parts[-1].strip().upper()
    if not cam_id:
        return None
    try:
        resp = http_session().get(
            page_url,
            timeout=(timeout, timeout * 3),
            verify=config.REQUEST_VERIFY_SSL,
            headers={"User-Agent": UA},
            allow_redirects=True,
        )
    except Exception:
        return None
    try:
        if not resp.ok:
            return None
        body = (resp.text or "").replace("\\/", "/")
    finally:
        resp.close()

    matches: list[str] = []
    cdn_prefix = rf"https://cameras-cam\.cdn\.weatherbug\.net/{re.escape(cam_id)}/"
    patterns = (
        rf'"image"\s*:\s*"({cdn_prefix}[^"]+?_l\.jpg)"',
        rf"rel=[\"']preload[\"']\s+as=[\"']image[\"']\s+href=[\"']({cdn_prefix}[^\"']+?_l\.jpg)",
        rf"{cdn_prefix}[^\s\"'\\]+?_l\.jpg",
    )
    for pattern in patterns:
        for match in re.findall(pattern, body):
            image_url = match if isinstance(match, str) else match[0]
            if image_url not in matches:
                matches.append(image_url)
    if not matches:
        return None
    return max(matches, key=_weatherbug_latest_sort_key)


def _template_flag_enabled(value) -> bool:
    """Return whether a DB/template boolean-like value is enabled."""

    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {
            "",
            "0",
            "false",
            "f",
            "no",
            "n",
            "off",
            "none",
            "null",
        }
    return bool(value)


def _earthcam_stream_extraction_allowed(force_browser: bool) -> bool:
    """Return True when an EarthCam page may be converted to a stream first."""

    # Explicit browser templates are usually configured that way because the
    # page/player screenshot is more reliable than short-lived signed streams.
    return not force_browser


def _template_uses_uid_cgi_snapshot(template: dict, url: str) -> bool:
    """Return True for cameras that need a UID before still capture."""

    driver = str(template.get("ptz_vendor_driver") or "").strip().lower()
    source_template = str(template.get("source_template") or "").strip().lower()
    path = urlparse(url).path.rstrip("/").lower()
    return (
        driver == "uid_cgi"
        or source_template == "uid_cgi_snapshot"
        or path.endswith("/cgi-bin/getuid")
    )


def _uid_cgi_snapshot_url(
    url: str,
    username: str | None,
    password: str | None,
    timeout: int,
) -> str | None:
    """Return a fresh UID-backed still URL for older UID/CGI PTZ cameras."""

    if not username or password is None:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    try:
        resp = http_session().get(
            f"{base_url}/cgi-bin/getuid",
            params={"username": username, "password": password},
            timeout=(max(1, timeout), max(2, timeout * 2)),
            verify=config.REQUEST_VERIFY_SSL,
            headers={"User-Agent": UA},
        )
    except Exception:
        return None
    try:
        if not getattr(resp, "ok", False):
            return None
        text = str(getattr(resp, "text", "") or "")
        match = re.search(r"<uid>([^<]+)</uid>", text, re.IGNORECASE)
        if not match:
            return None
        uid = match.group(1).strip()
        if not uid:
            return None
        return f"{base_url}/cgi-bin/snapshot.cgi?{urlencode({'uid': uid})}"
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _wetmet_extract_stream_url(
    page_url: str,
    timeout: int = 30,
    proxy: str | None = None,
) -> str | None:
    """Extract the signed HLS stream from a Wetmet/WMVision widget page."""

    parsed_page = urlparse(page_url)
    if not re.search(r"(^|\.)wetmet\.net$", parsed_page.netloc, flags=re.I):
        return None
    if "/widgets/stream/frame.php" not in parsed_page.path.lower():
        return None
    request_kwargs = dict(
        timeout=(timeout, timeout * 2),
        verify=config.REQUEST_VERIFY_SSL,
        headers={"User-Agent": UA},
        allow_redirects=True,
    )
    proxy = validate_proxy(proxy)
    if proxy:
        request_kwargs["proxies"] = {"http": proxy, "https": proxy}
    try:
        resp = http_session().get(page_url, **request_kwargs)
    except Exception:
        return None
    try:
        if not resp.ok:
            return None
        body = str(resp.text or "").replace("\\/", "/")
    finally:
        resp.close()
    patterns = (
        r"\b(?:vurl|purl)\s*=\s*['\"]([^'\"]+?\.m3u8[^'\"]*)['\"]",
        r"src\s*:\s*['\"]([^'\"]+?\.m3u8[^'\"]*)['\"]",
        r"https://[^'\"\s<>]+?\.m3u8[^'\"\s<>]*",
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            stream_url = match.group(1) if match.lastindex else match.group(0)
            return stream_url.replace("&amp;", "&").strip()
    return None


def _rtspme_extract_stream_url(
    page_url: str,
    timeout: int = 30,
    proxy: str | None = None,
) -> str | None:
    """Extract a signed HLS stream from rtsp.me embeds or pages containing one."""

    def fetch(url: str) -> str | None:
        request_kwargs = dict(
            timeout=(timeout, timeout * 2),
            verify=config.REQUEST_VERIFY_SSL,
            headers={"User-Agent": UA},
            allow_redirects=True,
        )
        normalized_proxy = validate_proxy(proxy)
        if normalized_proxy:
            request_kwargs["proxies"] = {
                "http": normalized_proxy,
                "https": normalized_proxy,
            }
        try:
            resp = http_session().get(url, **request_kwargs)
        except Exception:
            return None
        try:
            if not resp.ok:
                return None
            return str(resp.text or "")
        finally:
            resp.close()

    parsed = urlparse(page_url)
    host = parsed.netloc.lower()
    if "rtsp.me" not in host:
        parent = fetch(page_url)
        if not parent:
            return None
        embed_match = re.search(
            r"https://[^'\"\s<>]*rtsp\.me/embed/[^'\"\s<>]+",
            parent,
            flags=re.IGNORECASE,
        )
        if not embed_match:
            return None
        body = fetch(embed_match.group(0).replace("&amp;", "&"))
    else:
        body = fetch(page_url)

    if not body:
        return None
    body = body.replace("\\/", "/")
    patterns = (
        r"https://[^'\"\s<>]+?\.m3u8[^'\"\s<>]*",
        r"\bsrc\s*=\s*['\"]([^'\"]+?\.m3u8[^'\"]*)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, body, flags=re.IGNORECASE)
        if match:
            stream_url = match.group(1) if match.lastindex else match.group(0)
            return stream_url.replace("&amp;", "&").strip()
    return None


def _cached_http_failure_blocks_capture(
    cached_status: int | None,
    *,
    force_browser: bool,
    url: str | None = None,
) -> bool:
    """Return whether a cached HTTP failure should stop this capture.

    Browser-backed sources often have intentionally different behavior from a
    cheap HTTP probe: an anti-bot 403, stale HEAD failure, or cached transient
    error should not prevent a configured browser capture from trying the
    actual page render path. Direct image/PDF/stream fetches still respect the
    cached failure to avoid hammering dead sources.
    """

    if (
        cached_status in {0, 502, 503, 504}
        and url
        and _is_limnotech_resized_image_url(url)
    ):
        return False
    return cached_status is not None and cached_status >= 400 and not force_browser


def _capture_or_download_inner(
    name: str,
    template: dict,
    url: str,
    clean_url: str,
    username: str | None,
    password: str | None,
) -> bool:
    sdm_webrtc_fallback = False
    # Capture the derived still image only after the preview page marks it ready.
    sdm_webrtc_selector = "//*[@id='stage']"

    # Resolve Eufy cloud bridge URLs (eufy://<profile>/<device_id>) to signed
    # local proxy URLs. This keeps cloud credentials inside Glimpser.
    if url.lower().startswith("eufy://"):
        try:
            url = resolve_eufy_to_snapshot(url)
            clean_url = sanitize_url(url)
        except EufyCloudError as exc:
            logging.warning(
                "Eufy bridge resolve failed for %s: %s", sanitize_url(url), exc
            )
            record_preflight_backoff(
                url, "eufy_resolve_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
            )
            _record_tier_failure(url, TIER_HTTP, "eufy_resolve_failed")
            return False

    # Resolve Google SDM camera URLs (sdm://<device_id>) to short-lived RTSP URLs.
    # For WEB_RTC-only cameras we fall back to a local, signed WebRTC preview page
    # that headless Chrome can snapshot.
    if url.lower().startswith("sdm://"):
        resolved = None
        try:
            resolved = resolve_sdm_to_rtsp(url)
        except GoogleSdmError as exc:
            msg = str(exc)
            if "WEB_RTC-only" in msg:
                preview_url = build_webrtc_preview_url(url)
                if preview_url:
                    sdm_webrtc_fallback = True
                    logging.info(
                        "SDM WEB_RTC fallback for %s via internal preview",
                        sanitize_url(url),
                    )
                    url = preview_url
                    clean_url = sanitize_url(url)
                else:
                    logging.warning(
                        "SDM WEB_RTC fallback failed to build preview URL for %s",
                        sanitize_url(url),
                    )
                    record_preflight_backoff(
                        url, "sdm_webrtc_preview_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
                    )
                    _record_tier_failure(url, TIER_HTTP, "sdm_webrtc_preview_failed")
                    return False
            else:
                logging.warning("SDM resolve failed for %s: %s", sanitize_url(url), exc)
                record_preflight_backoff(
                    url, "sdm_resolve_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
                )
                _record_tier_failure(url, TIER_HTTP, "sdm_resolve_failed")
                return False
        if not sdm_webrtc_fallback and not resolved:
            record_preflight_backoff(
                url, "sdm_unconfigured", PREFLIGHT_BACKOFF_STREAM_FAIL
            )
            _record_tier_failure(url, TIER_HTTP, "sdm_unconfigured")
            return False
        if not sdm_webrtc_fallback:
            url = resolved
            clean_url = sanitize_url(url)

    authed_rtsp_url = _rtsp_url_with_credentials(url, username, password)
    if authed_rtsp_url != url:
        url = authed_rtsp_url
        clean_url = sanitize_url(url)

    popup_xpath = template.get("popup_xpath")
    dedicated_selector = template.get("dedicated_xpath")
    timeout = int(template.get("timeout", 30) or 30)

    # Set flags based on template parameters
    invert = _template_flag_enabled(template.get("invert"))
    headless = _template_flag_enabled(template.get("headless"))
    dark = _template_flag_enabled(template.get("dark"))
    stealth = _template_flag_enabled(template.get("stealth"))
    browser = _template_flag_enabled(template.get("browser"))
    danger = _template_flag_enabled(template.get("danger"))
    stabilize_mode = _normalize_stabilize_mode(template.get("stabilize_mode"))
    danger_fallback = _danger_fallback_active(url)
    is_hdhomerun_stream = _is_hdhomerun_like_stream_url(url)
    effective_stream_burst_frames, effective_stream_burst_span_ms = (
        _effective_stream_burst_settings(
            url,
            template,
            is_hdhomerun_stream=is_hdhomerun_stream,
        )
    )

    if sdm_webrtc_fallback:
        browser = True
        headless = True
        stealth = False
        timeout = max(timeout, 40)
        if not dedicated_selector:
            dedicated_selector = sdm_webrtc_selector

    if danger:
        browser = True
        headless = True

    force_browser = bool(browser or danger or popup_xpath or dedicated_selector)
    if danger and not _danger_chrome_available():
        record_preflight_backoff(
            url, "danger_unavailable", PREFLIGHT_BACKOFF_BROWSER_FAIL
        )
        _record_tier_failure(url, TIER_HUMAN, "danger_unavailable")
        return False
    if not (username or password) and _get_auth_hint(url):
        _record_tier_failure(url, TIER_HTTP, "auth_required")
        return False

    # Check if the host is reachable for network URLs
    parsed = urlparse(url)
    domain, port = parse_url(url)
    scheme = parsed.scheme.lower()
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "rtsp":
            port = 554
        elif scheme == "rtsps":
            port = 322
        elif scheme == "rtmp":
            port = 1935
        else:
            port = 80

    rtsp_preflight_ok = False
    rtsp_preflight_url = None
    lan_fast_reachable: bool | None = None

    if domain and _is_lan_target(domain):
        if scheme == "rtsps" and parsed.port is None:
            # parse_url retains a legacy public Google RTSPS default of 443;
            # ordinary LAN RTSPS endpoints use 322 unless explicitly configured.
            port = 322
        quarantined, remaining = _local_quarantine_active(url)
        if quarantined:
            logging.debug(
                "Local quarantine active for %s: %ds",
                clean_url,
                remaining,
            )
            return False
        state = network_state()
        if not state.get("lan_ok", True):
            record_preflight_backoff(
                url, "lan_offline", PREFLIGHT_BACKOFF_LOCAL_UNREACHABLE
            )
            _record_tier_failure(url, TIER_NETWORK, "lan_offline")
            return False
        # Quick LAN probe to fail fast on dead ports and reduce preflight CPU
        # churn under unstable local networks.
        # `port` already resolves an explicit URL port or the scheme default.
        # A different service on the default port cannot establish that this
        # camera endpoint is reachable.
        fast_timeout = max(0.2, float(PREFLIGHT_LAN_FAST_PROBE_TIMEOUT))
        lan_fast_reachable = is_address_reachable(
            domain, port=port, timeout=fast_timeout
        )
        if not lan_fast_reachable:
            logging.info(
                "Fast LAN preflight blocked %s (port=%s)",
                clean_url,
                port,
            )
            record_preflight_backoff(
                url,
                "local_unreachable_fast",
                PREFLIGHT_BACKOFF_LOCAL_UNREACHABLE,
            )
            _record_tier_failure(url, TIER_NETWORK, "unreachable")
            return False

    if scheme == "rtsp":
        if not _tier_allowed(url, TIER_NETWORK):
            logging.debug("Tier lockout for %s at network tier", clean_url)
            return False
        rtsp_url = _get_rtsp_profile_url(url) or url
        if not _rtsp_options_probe(rtsp_url):
            candidate = _probe_rtsp_variant(url)
            if candidate:
                rtsp_url = candidate
            if not _rtsp_options_probe(rtsp_url):
                backoff_active = _record_rtsp_preflight_failure(url, "options_failed")
                if not backoff_active:
                    logging.warning(
                        "RTSP preflight blocked %s (options failed)", clean_url
                    )
                record_preflight_backoff(
                    url, "rtsp_unreachable", PREFLIGHT_BACKOFF_STREAM_FAIL
                )
                _record_tier_failure(url, TIER_NETWORK, "rtsp_unreachable")
                return False
        if _rtsp_auth_required(rtsp_url):
            logging.warning("RTSP preflight blocked %s (auth required)", clean_url)
            _record_tier_failure(url, TIER_NETWORK, "rtsp_auth_required")
            return False
        describe_ok, codec = _rtsp_describe_probe(rtsp_url)
        if describe_ok is False:
            candidate = _probe_rtsp_variant(url)
            if candidate:
                rtsp_url = candidate
                describe_ok, codec = _rtsp_describe_probe(rtsp_url)
            if describe_ok is False:
                backoff_active = _record_rtsp_preflight_failure(url, "describe_failed")
                if not backoff_active:
                    logging.warning(
                        "RTSP preflight blocked %s (describe failed)", clean_url
                    )
                record_preflight_backoff(
                    url, "rtsp_describe_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
                )
                _record_tier_failure(url, TIER_NETWORK, "rtsp_describe_failed")
                return False
        if codec:
            _set_codec_cache(url, codec)
        if _rtsp_keepalive_ok(rtsp_url) is None:
            _rtsp_keepalive_probe(rtsp_url)
        rtsp_preflight_ok = True
        rtsp_preflight_url = rtsp_url

        if parsed.scheme in {"http", "https"}:
            active, reason, remaining = _domain_backoff_active(url)
            if active:
                now = time.time()
                key = _domain_key(url) or clean_url
                last = _domain_backoff_log_cache.get(key, 0.0)
                if now - last >= DOMAIN_BACKOFF_LOG_INTERVAL:
                    _domain_backoff_log_cache[key] = now
                    logging.info(
                        "Domain backoff active for %s (%s): %ds",
                        clean_url,
                        reason or "unknown",
                        remaining,
                    )
                return False

    if domain:
        if not _tier_allowed(url, TIER_NETWORK):
            logging.debug("Tier lockout for %s at network tier", clean_url)
            return False
        if parsed.scheme in {"http", "https"}:
            dns_tls_ok, dns_tls_reason = _preflight_dns_tls(url)
            if not dns_tls_ok:
                _record_tier_failure(url, TIER_NETWORK, dns_tls_reason)
                return False
        if lan_fast_reachable is True:
            lreach = True
        else:
            lreach = is_address_reachable(domain, port=port)
        if lreach is False:
            logging.debug(f"Could not reach host: {name} {clean_url}")
            cas_error(url)
            if _is_private_host(domain):
                logging.warning("LAN preflight blocked %s (unreachable)", clean_url)
                record_preflight_backoff(
                    url,
                    "local_unreachable",
                    PREFLIGHT_BACKOFF_LOCAL_UNREACHABLE,
                )
            _record_tier_failure(url, TIER_NETWORK, "unreachable")
            return False
        _record_tier_success(url, TIER_NETWORK, "reachable")

    # Prepare output path
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    output_path = os.path.join(SCREENSHOT_DIRECTORY, f"{name}/{name}_{timestamp}.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if _template_uses_uid_cgi_snapshot(template, url) and not (danger or browser):
        snapshot_url = _uid_cgi_snapshot_url(url, username, password, timeout)
        if snapshot_url:
            lsuc = download_image(
                snapshot_url,
                output_path,
                timeout,
                name,
                invert,
                dark,
                stealth,
                template.get("proxy"),
                None,
                None,
                stabilize_mode=stabilize_mode,
                source_identity=template.get("source_template")
                or template.get("url")
                or url,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "uid_cgi_snapshot_downloaded")
                _set_method_preference(url, "snapshot")
                _clear_danger_fallback(url)
                return lsuc
            if is_stale_capture_result(lsuc):
                return lsuc
            _record_tier_failure(url, TIER_HTTP, "uid_cgi_snapshot_download_failed")
        else:
            _record_tier_failure(url, TIER_HTTP, "uid_cgi_auth_failed")
        record_preflight_backoff(
            url, "uid_cgi_snapshot_failed", PREFLIGHT_BACKOFF_REQUEST_FAIL
        )
        return False

    if _is_weatherbug_camera_url(url) and not danger:
        img_url = _weatherbug_extract_latest_image(url, timeout)
        if img_url:
            lsuc = download_image(
                img_url,
                output_path,
                timeout,
                name,
                invert,
                dark,
                stealth,
                template.get("proxy"),
                username,
                password,
                stabilize_mode=stabilize_mode,
                source_identity=template.get("source_template")
                or template.get("url")
                or url,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "weatherbug_image_extracted")
                _set_method_preference(url, "snapshot")
                _clear_danger_fallback(url)
                return lsuc
            if is_stale_capture_result(lsuc):
                return lsuc

    if _is_limnotech_resized_image_url(url) and not (danger or browser):
        limnotech_connect_timeout = min(timeout, 10)
        limnotech_read_timeout = min(max(timeout, 12), 15)
        lsuc = download_image(
            url,
            output_path,
            limnotech_connect_timeout,
            name,
            invert,
            dark,
            stealth,
            template.get("proxy"),
            username,
            password,
            stabilize_mode=stabilize_mode,
            read_timeout=limnotech_read_timeout,
            source_identity=template.get("source_template")
            or template.get("url")
            or url,
        )
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "limnotech_image_downloaded")
            _set_method_preference(url, "snapshot")
            _clear_danger_fallback(url)
            return lsuc
        if is_stale_capture_result(lsuc):
            return lsuc
        if _has_existing_screenshot(name):
            logging.warning(
                "[%s] Keeping previous LimnoTech buoy frame after transient failure",
                name,
            )
            record_preflight_backoff(
                url, "limnotech_transient_failure", PREFLIGHT_BACKOFF_REQUEST_FAIL
            )
            _record_tier_success(url, TIER_HTTP, "limnotech_previous_frame_kept")
            return CAPTURE_STALE_PREVIOUS

    # Determine content type
    if not _tier_allowed(url, TIER_HTTP):
        logging.debug("Tier lockout for %s at HTTP tier", clean_url)
        return False
    if _has_redirect_loop(url):
        auth = get_preferred_auth(url, username, password)
        if auth:
            # Redirect-loop cache can get stuck on camera/login flows.
            # If we have credentials, clear it and attempt once.
            redirect_loop_cache.pop(url, None)
            redirect_loop_cache_time.pop(url, None)
            _persist_preflight_cache()
        else:
            _record_tier_failure(url, TIER_HTTP, "redirect_loop")
            return False
    cached_http_error = _get_http_error(url)
    if _cached_http_failure_blocks_capture(
        cached_http_error, force_browser=force_browser, url=url
    ):
        _record_tier_failure(url, TIER_HTTP, f"http_{cached_http_error}")
        return False
    if _content_anomaly_active(url) or _has_content_mismatch(url):
        _record_tier_failure(url, TIER_HTTP, "content_mismatch")
        return False
    if _has_cookie_wall(url) and not (username or password):
        _record_tier_failure(url, TIER_HTTP, "cookie_wall")
        return False
    if _has_content_mismatch(url):
        _record_tier_failure(url, TIER_HTTP, "content_mismatch")
        return False
    if _has_cookie_wall(url) and not (username or password):
        _record_tier_failure(url, TIER_HTTP, "cookie_wall")
        return False
    content_type, is_modified, preflight_ok, preflight_reason = get_content_type(
        url, danger, stealth=stealth, username=username, password=password
    )
    if throttle_cache.get(url) and throttle_cache[url].get("timeout", 0) > time.time():
        return False

    if not preflight_ok:
        _record_tier_failure(url, TIER_HTTP, preflight_reason)
        if preflight_reason in {"offline", "request_failed"}:
            record_preflight_backoff(
                url, preflight_reason, PREFLIGHT_BACKOFF_REQUEST_FAIL
            )
        if preflight_reason == "rate_limited" or not force_browser:
            return False
    else:
        _record_tier_success(url, TIER_HTTP, preflight_reason)

    content_kind = None
    if is_image_url(url, content_type):
        content_kind = "image"
    elif is_pdf_url(url, content_type):
        content_kind = "pdf"
    elif is_video_stream_url(url, content_type):
        content_kind = "stream"

    allow_browser_fallback = force_browser or content_kind is None
    last_latency = _get_latency(url)
    if last_latency is not None and last_latency > PRELIGHT_LATENCY_THRESHOLD:
        _record_tier_failure(url, TIER_HTTP, "latency_guard")
        allow_browser_fallback = False
    content_length = _get_content_length(url)
    if (
        content_length
        and content_length > PREFLIGHT_MAX_BYTES
        and content_kind in {"image", "pdf"}
        and not force_browser
    ):
        _record_tier_failure(url, TIER_HTTP, "payload_too_large")
        record_preflight_backoff(
            url, "payload_too_large", PREFLIGHT_BACKOFF_REQUEST_FAIL
        )
        return False

    if content_type.startswith("text/html"):
        if is_modified is False:
            _record_html_stable(url)
            if allow_browser_fallback and _html_stable_active(url) and not danger:
                # HTML validators describe the document, not embedded camera
                # frames, dashboards, or JavaScript-fetched data.
                logging.debug(
                    "HTML unchanged; refreshing embedded content for %s", clean_url
                )
        if (
            content_length
            and content_length > PREFLIGHT_HTML_MAX_BYTES
            and not force_browser
        ):
            logging.info(
                "HTML payload too large; skipping heavy render for %s", clean_url
            )
            record_preflight_backoff(
                url, "html_payload_too_large", PREFLIGHT_BACKOFF_REQUEST_FAIL
            )
            _record_tier_failure(url, TIER_HTTP, "html_payload_too_large")
            allow_browser_fallback = False

    # Recheck image bytes even when a shared HEAD validator is unchanged:
    # another camera may own that cached validator, and source-age evidence
    # must describe this camera's accepted pixels. The downloader deduplicates.
    if (
        is_modified is False
        and content_kind == "pdf"
        and not danger
        and not browser
        and _has_existing_screenshot(name)
    ):
        _record_tier_success(url, TIER_HTTP, "not_modified")
        _clear_danger_fallback(url)
        return CAPTURE_STALE_PREVIOUS

    # Attempt to download or capture based on content type and URL
    if content_type.startswith("text/html") and not danger:
        wetmet_stream_url = _wetmet_extract_stream_url(
            url,
            timeout=timeout,
            proxy=template.get("proxy"),
        )
        if wetmet_stream_url and _method_allowed(url, "stream"):
            lsuc = capture_frame_from_stream(
                wetmet_stream_url,
                output_path,
                timeout,
                name,
                invert,
                stabilize_mode=stabilize_mode,
                stream_burst_frames=effective_stream_burst_frames,
                stream_burst_span_ms=effective_stream_burst_span_ms,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "wetmet_stream_extracted")
                _record_method_success(url, "stream")
                _set_method_preference(url, "stream")
                _clear_danger_fallback(url)
                return lsuc
        cas_error(url)

        rtspme_stream_url = _rtspme_extract_stream_url(
            url,
            timeout=timeout,
            proxy=template.get("proxy"),
        )
        if rtspme_stream_url and _method_allowed(url, "stream"):
            lsuc = capture_frame_from_stream(
                rtspme_stream_url,
                output_path,
                timeout,
                name,
                invert,
                stabilize_mode=stabilize_mode,
                stream_burst_frames=effective_stream_burst_frames,
                stream_burst_span_ms=effective_stream_burst_span_ms,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "rtspme_stream_extracted")
                _record_method_success(url, "stream")
                _set_method_preference(url, "stream")
                _clear_danger_fallback(url)
                return lsuc

        earthcam_stream_url = None
        if _earthcam_stream_extraction_allowed(force_browser):
            earthcam_stream_url = _earthcam_extract_stream_url(
                url,
                timeout=timeout,
                proxy=template.get("proxy"),
            )
        if earthcam_stream_url and _method_allowed(url, "stream"):
            lsuc = capture_frame_from_stream(
                earthcam_stream_url,
                output_path,
                timeout,
                name,
                invert,
                stabilize_mode=stabilize_mode,
                stream_burst_frames=effective_stream_burst_frames,
                stream_burst_span_ms=effective_stream_burst_span_ms,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "earthcam_stream_extracted")
                _record_method_success(url, "stream")
                _set_method_preference(url, "stream")
                _clear_danger_fallback(url)
                return lsuc
        img_url = _weatherbug_extract_latest_image(url, timeout)
        if img_url:
            lsuc = download_image(
                img_url,
                output_path,
                timeout,
                name,
                invert,
                dark,
                stealth,
                template.get("proxy"),
                username,
                password,
                stabilize_mode=stabilize_mode,
                source_identity=template.get("source_template")
                or template.get("url")
                or url,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "weatherbug_image_extracted")
                _set_method_preference(url, "snapshot")
                _clear_danger_fallback(url)
                return lsuc
            if is_stale_capture_result(lsuc):
                return lsuc

    if is_image_url(url, content_type) and not danger and not browser:
        lsuc = download_image(
            url,
            output_path,
            timeout,
            name,
            invert,
            dark,
            stealth,
            template.get("proxy"),
            username,
            password,
            stabilize_mode=stabilize_mode,
            source_identity=template.get("source_template")
            or template.get("url")
            or url,
        )
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "image_downloaded")
            _clear_danger_fallback(url)
            return lsuc
        if is_stale_capture_result(lsuc):
            return lsuc
        cas_error(url)
        _record_tier_failure(url, TIER_HTTP, "image_download_failed")

    if is_pdf_url(url, content_type) and not danger and not browser:
        lsuc = download_pdf(
            url,
            output_path,
            timeout,
            name,
            invert,
            dark,
            stealth,
            username,
            password,
            stabilize_mode=stabilize_mode,
        )
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "pdf_downloaded")
            _clear_danger_fallback(url)
            return lsuc
        cas_error(url)
        _record_tier_failure(url, TIER_HTTP, "pdf_download_failed")

    if is_video_stream_url(url, content_type) and not danger and not browser:
        cached_codec = _get_codec_cache(url)
        cached_fingerprint = _get_stream_fingerprint(url)
        fingerprint_codec = None
        if cached_fingerprint:
            fingerprint_codec = cached_fingerprint.get("codec")
        if not _codec_supported(cached_codec or fingerprint_codec):
            record_preflight_backoff(
                url, "unsupported_codec", PREFLIGHT_BACKOFF_STREAM_FAIL
            )
            _record_tier_failure(url, TIER_HTTP, "unsupported_codec")
            return False
        rtsp_url = rtsp_preflight_url or url
        if urlparse(url).scheme.lower() == "rtsp" and not rtsp_preflight_ok:
            if rtsp_url == url:
                rtsp_url = _get_rtsp_profile_url(url) or url
            if not _rtsp_options_probe(rtsp_url):
                if rtsp_url == url:
                    candidate = _probe_rtsp_variant(url)
                    if candidate:
                        rtsp_url = candidate
                if not _rtsp_options_probe(rtsp_url):
                    _record_rtsp_preflight_failure(url, "options_failed")
                    record_preflight_backoff(
                        url, "rtsp_unreachable", PREFLIGHT_BACKOFF_STREAM_FAIL
                    )
                    _record_tier_failure(url, TIER_NETWORK, "rtsp_unreachable")
                    return False
            if _rtsp_auth_required(rtsp_url):
                _record_tier_failure(url, TIER_NETWORK, "rtsp_auth_required")
                return False
            describe_ok, codec = _rtsp_describe_probe(rtsp_url)
            if describe_ok is False:
                if rtsp_url == url:
                    candidate = _probe_rtsp_variant(url)
                    if candidate:
                        rtsp_url = candidate
                        describe_ok, codec = _rtsp_describe_probe(rtsp_url)
                if describe_ok is False:
                    _record_rtsp_preflight_failure(url, "describe_failed")
                    snapshot_url = _probe_snapshot_url(
                        rtsp_url, username=username, password=password
                    )
                    if snapshot_url:
                        lsuc = download_image(
                            snapshot_url,
                            output_path,
                            timeout,
                            name,
                            invert,
                            dark,
                            stealth,
                            template.get("proxy"),
                            username,
                            password,
                            stabilize_mode=stabilize_mode,
                            source_identity=template.get("source_template")
                            or template.get("url")
                            or url,
                        )
                        if lsuc is True:
                            _record_tier_success(url, TIER_HTTP, "snapshot_downloaded")
                            _set_method_preference(url, "snapshot")
                            _clear_danger_fallback(url)
                            return lsuc
                        if is_stale_capture_result(lsuc):
                            return lsuc
                    record_preflight_backoff(
                        url, "rtsp_describe_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
                    )
                    _record_tier_failure(url, TIER_NETWORK, "rtsp_describe_failed")
                    return False
            if codec:
                _set_codec_cache(url, codec)
            if _rtsp_keepalive_ok(rtsp_url) is None:
                _rtsp_keepalive_probe(rtsp_url)
        if not _method_allowed(url, "stream"):
            logging.debug("Method backoff for %s (stream)", clean_url)
            return False
        cached_codec = _get_codec_cache(url)
        if not _codec_supported(cached_codec):
            record_preflight_backoff(
                url, "unsupported_codec", PREFLIGHT_BACKOFF_STREAM_FAIL
            )
            _record_tier_failure(url, TIER_HTTP, "unsupported_codec")
            return False
        if (
            "mjpg" in url.lower()
            or "mjpeg" in url.lower()
            or "multipart" in content_type
        ):
            if not _probe_mjpeg(url, username, password):
                record_preflight_backoff(
                    url, "mjpeg_probe_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
                )
                _record_tier_failure(url, TIER_HTTP, "mjpeg_probe_failed")
                return False
        # Re-evaluate burst settings after RTSP preflight so stream
        # fingerprints learned during describe/ffprobe can influence the
        # still-capture burst shape for low-fps cameras.
        effective_stream_burst_frames, effective_stream_burst_span_ms = (
            _effective_stream_burst_settings(
                rtsp_url,
                template,
                is_hdhomerun_stream=is_hdhomerun_stream,
            )
        )
        lsuc = capture_frame_from_stream(
            rtsp_url,
            output_path,
            timeout,
            name,
            invert,
            stabilize_mode=stabilize_mode,
            stream_burst_frames=effective_stream_burst_frames,
            stream_burst_span_ms=effective_stream_burst_span_ms,
        )
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "stream_captured")
            _record_method_success(url, "stream")
            _set_method_preference(url, "stream")
            _clear_danger_fallback(url)
            return lsuc

        snapshot_url = None
        if urlparse(url).scheme.lower() == "rtsp":
            # Cold snapshot discovery can be slow on port-forwarded camera
            # sites. Normal RTSP capture should not block on that scan after a
            # stream timeout; only use a snapshot URL that was already proven.
            snapshot_url = _get_snapshot_probe(rtsp_url)
        if snapshot_url:
            lsuc = download_image(
                snapshot_url,
                output_path,
                timeout,
                name,
                invert,
                dark,
                stealth,
                template.get("proxy"),
                username,
                password,
                stabilize_mode=stabilize_mode,
                source_identity=template.get("source_template")
                or template.get("url")
                or url,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "snapshot_downloaded")
                _set_method_preference(url, "snapshot")
                _clear_danger_fallback(url)
                return lsuc
            if is_stale_capture_result(lsuc):
                return lsuc

        cas_error(url)
        record_preflight_backoff(
            url, "stream_capture_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
        )
        _record_tier_failure(url, TIER_HTTP, "stream_capture_failed")
        _record_method_failure(url, "stream", STREAM_BACKOFF_BASE)

    if (
        is_enhanced(url) and not danger and not browser
    ):  # this is going to launch ytdlp, which is not a browser
        if not _method_allowed(url, "ytdlp"):
            logging.debug("Method backoff for %s (ytdlp)", clean_url)
            return False
        lsuc = capture_frame_with_ytdlp(
            url,
            output_path,
            name,
            invert,
            stabilize_mode=stabilize_mode,
        )
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "ytdlp_captured")
            _record_method_success(url, "ytdlp")
            _set_method_preference(url, "ytdlp")
            _clear_danger_fallback(url)
            return lsuc
        cas_error(url)
        record_preflight_backoff(url, "ytdlp_failed", PREFLIGHT_BACKOFF_YTDLP_FAIL)
        _record_tier_failure(url, TIER_HTTP, "ytdlp_failed")
        _record_method_failure(url, "ytdlp", YTDLP_BACKOFF_BASE)

    preferred_method = _get_method_preference(url)
    browser_methods = ["lightweight", "phantom", "headless"]
    if preferred_method in browser_methods:
        browser_methods.remove(preferred_method)
        browser_methods.insert(0, preferred_method)

    for method in browser_methods:
        if not allow_browser_fallback:
            break
        if preferred_method in {"snapshot", "stream", "ytdlp"}:
            logging.debug(
                "Preferred method %s for %s; skipping browser fallback",
                preferred_method,
                clean_url,
            )
            break

        if method == "lightweight":
            if not _renderer_healthy("lightweight"):
                logging.info(
                    "Renderer backoff active for lightweight; skipping %s", clean_url
                )
                continue
            if not should_use_lightweight_browser(
                url,
                dedicated_selector,
                popup_xpath,
                headless,
                stealth,
                browser,
                danger,
                name=name,
            ):
                continue
            if not _tier_allowed(url, TIER_LIGHT_RENDER):
                logging.debug("Tier lockout for %s at light renderer tier", clean_url)
                return False
            if not _method_allowed(url, "lightweight"):
                logging.debug("Method backoff for %s (lightweight)", clean_url)
                continue
            method_start = time.time()
            lsuc = capture_screenshot_and_har_light(
                url,
                output_path,
                timeout,
                name,
                invert,
                template.get("proxy"),
                dark,
                stabilize_mode=stabilize_mode,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_LIGHT_RENDER, "lightweight_capture")
                _record_method_success(url, "lightweight")
                _set_method_preference(url, "lightweight")
                _clear_renderer_failure("lightweight")
                _clear_danger_fallback(url)
                return lsuc
            if time.time() - method_start > timeout:
                logging.error(f"   *fail lightweight {clean_url}")
                cas_error(url)
                _record_renderer_failure("lightweight", "timeout")
                _record_browser_failure_for_danger(url, "lightweight_timeout")
                record_preflight_backoff(
                    url, "lightweight_timeout", PREFLIGHT_BACKOFF_BROWSER_FAIL
                )
                _record_tier_failure(url, TIER_LIGHT_RENDER, "lightweight_timeout")
                _record_method_failure(url, "lightweight", LIGHT_RENDER_BACKOFF_BASE)
            else:
                _record_renderer_failure("lightweight", "failed")
                _record_browser_failure_for_danger(url, "lightweight_failed")
                _record_tier_failure(
                    url, TIER_LIGHT_RENDER, "lightweight_failed", lock=False
                )
                _record_method_failure(url, "lightweight", LIGHT_RENDER_BACKOFF_BASE)

        elif method == "phantom":
            if not _renderer_healthy("phantom"):
                logging.info(
                    "Renderer backoff active for phantom; skipping %s", clean_url
                )
                continue
            if not should_use_phantom_browser(
                url,
                dedicated_selector,
                popup_xpath,
                headless,
                stealth,
                browser,
                danger,
                name=name,
            ):
                continue
            if not _tier_allowed(url, TIER_LIGHT_RENDER):
                logging.debug("Tier lockout for %s at light renderer tier", clean_url)
                return False
            if not _method_allowed(url, "phantom"):
                logging.debug("Method backoff for %s (phantom)", clean_url)
                continue
            method_start = time.time()
            lsuc = capture_screenshot_phantom(
                url=url,
                output_path=output_path,
                timeout=timeout,
                name=name,
                dedicated_selector=dedicated_selector,
                invert=invert,
                dark=dark,
                stabilize_mode=stabilize_mode,
            )
            if lsuc is True:
                _record_tier_success(url, TIER_LIGHT_RENDER, "phantom_capture")
                _record_method_success(url, "phantom")
                _set_method_preference(url, "phantom")
                _clear_renderer_failure("phantom")
                _clear_danger_fallback(url)
                return lsuc
            if time.time() - method_start > timeout:
                logging.error(f"   *fail phantom {clean_url} ")
                cas_error(url)
                _record_renderer_failure("phantom", "timeout")
                _record_browser_failure_for_danger(url, "phantom_timeout")
                record_preflight_backoff(
                    url, "phantom_timeout", PREFLIGHT_BACKOFF_BROWSER_FAIL
                )
                _record_tier_failure(url, TIER_LIGHT_RENDER, "phantom_timeout")
                _record_method_failure(url, "phantom", PHANTOM_BACKOFF_BASE)
            else:
                _record_renderer_failure("phantom", "failed")
                _record_browser_failure_for_danger(url, "phantom_failed")
                _record_tier_failure(url, TIER_LIGHT_RENDER, "phantom_failed")
                _record_method_failure(url, "phantom", PHANTOM_BACKOFF_BASE)

        elif method == "headless":
            if not _renderer_healthy("headless"):
                logging.info(
                    "Renderer backoff active for headless; skipping %s", clean_url
                )
                continue
            if not re.findall(r"^https?://", url, flags=re.I):
                continue
            use_danger = danger
            if danger_fallback and not danger:
                if _danger_fallback_ready(url, clean_url):
                    use_danger = True
                else:
                    use_danger = False
            target_tier = TIER_HUMAN if use_danger else TIER_HEADLESS
            if not _tier_allowed(url, target_tier):
                logging.debug(
                    "Tier lockout for %s at %s tier",
                    clean_url,
                    TIER_NAMES.get(target_tier, target_tier),
                )
                return False
            if not _method_allowed(url, "headless"):
                logging.debug("Method backoff for %s (headless)", clean_url)
                continue
            method_start = time.time()
            lsuc = capture_screenshot_and_har(
                url=url,
                output_path=output_path,
                popup_xpath=popup_xpath,
                dedicated_selector=dedicated_selector,
                timeout=timeout,
                name=name,
                invert=invert,
                proxy=template.get("proxy"),
                dark=dark,
                stealth=stealth,
                danger=use_danger,
                stabilize_mode=stabilize_mode,
                allow_sparse_capture=(
                    str(template.get("source_template") or "").lower()
                    in {"hubitat_cloud_dashboard", "ais_map", "map_dashboard"}
                    or _is_hubitat_cloud_dashboard_url(url)
                ),
            )
            if lsuc is True:
                detail = "danger_capture" if use_danger else "headless_capture"
                _record_tier_success(url, target_tier, detail)
                _record_method_success(url, "headless")
                _set_method_preference(url, "headless")
                _clear_renderer_failure("headless")
                _clear_danger_fallback(url)
                return lsuc

            if is_stale_capture_result(lsuc):
                return lsuc

            if not use_danger:
                is_sdm_webrtc_preview = "/integrations/google/webrtc/preview" in str(
                    url or ""
                )
                method_backoff = 45 if is_sdm_webrtc_preview else HEADLESS_BACKOFF_BASE
                preflight_backoff = (
                    45 if is_sdm_webrtc_preview else PREFLIGHT_BACKOFF_BROWSER_FAIL
                )
                preserve_specific_reason = _has_specific_hubitat_preflight_reason(
                    url
                ) or (
                    str((throttle_cache.get(url) or {}).get("reason") or "")
                    in {"browser_error_page", "sdm_preview_not_ready"}
                )
                cas_error(url)
                if time.time() - method_start > timeout:
                    _record_browser_failure_for_danger(url, "headless_timeout")
                    if not preserve_specific_reason:
                        record_preflight_backoff(
                            url,
                            "browser_timeout",
                            preflight_backoff,
                        )
                    _record_tier_failure(url, target_tier, "browser_timeout")
                    _record_method_failure(url, "headless", method_backoff)
                else:
                    _record_browser_failure_for_danger(url, "headless_failed")
                    _record_tier_failure(url, target_tier, "browser_failed")
                    _record_method_failure(url, "headless", method_backoff)

    if not (danger or danger_fallback):
        # logging.error(" *** fail ", url, "brow", browser, "headless", headless, "stealth", stealth, "danger", danger, "dedicated", dedicated_selector, "popup", popup_xpath)
        logging.error(f"Failed to capture or download content from {clean_url}")

    return False


def capture_or_download(name: str, template: dict) -> bool:
    """
    Decides whether to download the image directly or capture a screenshot based on the given template.

    This function is the main entry point for capturing or downloading content from a URL. It handles
    various types of content (images, PDFs, video streams, web pages) and uses different methods to
    obtain the content based on the URL and content type.

    Args:
        name (str): The name to be used for the output file.
        template (dict): A dictionary containing configuration parameters for the capture/download.

    Returns:
        bool: True if the capture/download was successful, False otherwise.
    """
    if name is None or template is None:
        return False

    # Extract parameters from the template
    url = template.get("url")
    username = template.get("auth_username")
    password = template.get("auth_password")
    clean_url = sanitize_url(url)
    domain, _ = parse_url(url)
    force_browser = bool(
        _template_flag_enabled(template.get("browser"))
        or _template_flag_enabled(template.get("danger"))
        or template.get("popup_xpath")
        or template.get("dedicated_xpath")
    )

    # Disallow local file paths to avoid unintended file disclosure
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {
        "http",
        "https",
        "rtsp",
        "rtsps",
        "rtmp",
        "sdm",
        "eufy",
    }:
        logging.error("Unsupported URL scheme: %s", parsed.scheme)
        _record_tier_failure(url, TIER_OFFLINE, "unsupported_scheme")
        return False

    # Short-circuit quickly when a private-host source is currently quarantined.
    # This avoids repeated expensive capture attempts while the backoff window
    # is active.
    if domain and _is_lan_target(domain):
        quarantined, remaining = _local_quarantine_active(url)
        if quarantined:
            now = time.time()
            key = _domain_key(url) or clean_url
            last = _local_quarantine_log_cache.get(key, 0.0)
            if now - last >= LOCAL_QUARANTINE_LOG_INTERVAL:
                _local_quarantine_log_cache[key] = now
                logging.info(
                    "Local quarantine active for %s: %ds",
                    clean_url,
                    remaining,
                )
            entry = throttle_cache.get(url, {})
            entry["timeout"] = max(entry.get("timeout", 0), now + max(remaining, 1))
            entry["reason"] = "local_quarantine"
            throttle_cache[url] = entry
            _record_tier_failure(url, TIER_OFFLINE, "local_quarantine")
            return False
    source_open, source_remaining = _source_circuit_active(url)
    if source_open:
        now = time.time()
        key = _source_circuit_key(url)
        last = _source_circuit_log_cache.get(key, 0.0)
        if now - last >= SOURCE_CIRCUIT_LOG_INTERVAL:
            _source_circuit_log_cache[key] = now
            logging.warning(
                "Source circuit open for %s (%ds remaining)",
                clean_url,
                source_remaining,
            )
        _record_tier_failure(url, TIER_OFFLINE, "source_circuit_open")
        return False
    if domain and not _is_lan_target(domain):
        # For public/external targets, avoid thrashing every source when WAN/DNS
        # is unstable. This system is mostly periodic snapshots, so a short
        # global pause is safer than repeated expensive failures.
        state = network_state()
        dns_ok = bool(state.get("dns_ok", True))
        wan_ok = bool(state.get("wan_ok", True))
        if not (dns_ok and wan_ok):
            reason = "dns_offline" if not dns_ok else "wan_offline"
            record_preflight_backoff(url, reason, PREFLIGHT_BACKOFF_WAN_OFFLINE)
            now = time.time()
            key = _domain_key(url) or clean_url
            last = _wan_offline_log_cache.get(key, 0.0)
            if now - last >= WAN_OFFLINE_LOG_INTERVAL:
                _wan_offline_log_cache[key] = now
                logging.warning(
                    "Network degraded; pausing external capture for %s (%s)",
                    clean_url,
                    reason,
                )
            _record_tier_failure(url, TIER_NETWORK, reason)
            return False
    entry = throttle_cache.get(url)
    if entry and entry.get("reason") == "etag_flip":
        # Discard obsolete content-change backoff left by an earlier version.
        throttle_cache.pop(url, None)
        entry = None
    if entry and entry.get("timeout", 0) > time.time():
        remaining = int(entry["timeout"] - time.time())
        reason = entry.get("reason", "backoff")
        logging.debug(
            "Skipping %s due to %s backoff (%ds remaining)",
            clean_url,
            reason,
            max(remaining, 0),
        )
        _record_tier_failure(url, TIER_OFFLINE, reason)
        return False
    if (
        lurl_cache.get(url, "none") != "good"
        and time.time() - lurl_cache_time.get(url, 0) < 3600
        and not force_browser
    ):  # try every 1 hour no matter what??
        _record_tier_failure(url, TIER_OFFLINE, "cached_bad")
        return False

    cached_status = get_cached_status_code(url)
    if _cached_http_failure_blocks_capture(
        cached_status, force_browser=force_browser, url=url
    ):
        logging.debug(f"Skipping {clean_url} due to cached status {cached_status}")
        _record_tier_failure(url, TIER_OFFLINE, f"cached_status_{cached_status}")
        return False

    if not _tier_allowed(url, TIER_OFFLINE):
        logging.debug("Tier lockout for %s at offline tier", clean_url)
        return False

    budget_ok, budget_remaining = _consume_domain_retry_budget(url)
    if not budget_ok:
        _set_domain_backoff(url, "retry_budget_exhausted", budget_remaining)
        entry = throttle_cache.get(url, {})
        entry["timeout"] = max(
            entry.get("timeout", 0), time.time() + max(budget_remaining, 1)
        )
        entry["reason"] = "retry_budget_exhausted"
        throttle_cache[url] = entry
        _record_tier_failure(url, TIER_OFFLINE, "retry_budget_exhausted")
        return False

    if not _try_acquire_domain(url):
        logging.debug("Domain concurrency limit reached for %s", clean_url)
        _record_tier_failure(url, TIER_NETWORK, "domain_busy")
        return False

    try:
        return _capture_or_download_inner(
            name, template, url, clean_url, username, password
        )
    finally:
        _release_domain(url)


def check_if_modified(url, headers) -> bool:
    """
    Determines if a URL has changed since the last request by checking Last-Modified and ETag headers.

    Args:
        url (str): The URL being checked.
        headers (dict): The response headers from the latest request.

    Returns:
        bool: True if the content is new or changed, False if unchanged.
    """
    last_modified = headers.get("Last-Modified")
    etag = headers.get("ETag")

    if last_modified and last_modified == last_modified_cache.get(url):
        _record_static_asset_stable(url)
        logging.debug("No Last-Modified change: %s", last_modified)
        return False  # No changes detected
    if etag and etag == etag_cache.get(url):
        _record_static_asset_stable(url)
        logging.debug("No ETag change: %s", etag_cache)
        return False  # No changes detected

    # Update cache with new values
    if last_modified:
        last_modified_cache[url] = last_modified
    if etag:
        # A new validator means new content, not a transport failure. Live
        # snapshots can legitimately change on every successful request.
        etag_flip_cache.pop(url, None)
        etag_cache[url] = etag
    if last_modified or etag:
        _persist_preflight_cache()
    if _url_looks_like_static_asset(url):
        static_asset_cache.pop(url, None)
        static_asset_cache_time.pop(url, None)

    return True  # Content has changed or was never checked before


def _get_accept_ranges(url: str) -> str | None:
    cached = accept_ranges_cache.get(url)
    if cached and accept_ranges_cache_time.get(url, 0) > time.time() - 60 * 60:
        return cached
    return None


def _set_accept_ranges(url: str, value: str | None) -> None:
    if not value:
        return
    accept_ranges_cache[url] = value
    accept_ranges_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_content_length(url: str) -> int | None:
    cached = content_length_cache.get(url)
    if (
        cached is not None
        and content_length_cache_time.get(url, 0) > time.time() - 60 * 60
    ):
        return cached
    return None


def _set_content_length(url: str, value: int | None) -> None:
    if value is None:
        return
    last = content_length_cache.get(url)
    if last:
        delta = abs(value - last) / max(last, 1)
        if (
            delta > PREFLIGHT_CONTENT_LENGTH_MAX_VARIANCE
            and not _is_direct_camera_snapshot_url(url)
            and not capture_policy.variable_size_image(url)
            and not _is_eufy_snapshot_proxy_url(url)
            # Hubitat cloud alternates a small error page and the full dashboard.
            # Let HTTP/browser validation decide, not the prior response size.
            and not (
                urlparse(url).hostname == "cloud.hubitat.com"
                and _is_hubitat_cloud_dashboard_url(url)
            )
        ):
            record_preflight_backoff(
                url, "content_length_variance", PREFLIGHT_BACKOFF_REQUEST_FAIL
            )
    content_length_cache[url] = value
    content_length_cache_time[url] = time.time()
    _persist_preflight_cache()


def _set_alpn(url: str, value: str | None) -> None:
    if not value:
        return
    alpn_cache[url] = value
    alpn_cache_time[url] = time.time()
    _persist_preflight_cache()


def _set_alt_svc(url: str, value: str | None) -> None:
    if not value:
        return
    if _h3_downgrade_active(url) or PREFLIGHT_FORCE_H3_DOWNGRADE:
        filtered = ",".join(
            part for part in value.split(",") if "h3" not in part.lower()
        ).strip()
        if filtered:
            alt_svc_cache[url] = filtered
        else:
            return
    else:
        alt_svc_cache[url] = value
    alt_svc_cache_time[url] = time.time()
    _persist_preflight_cache()


def _h3_downgrade_active(url: str) -> bool:
    entry = h3_downgrade_cache.get(url)
    if (
        entry
        and h3_downgrade_cache_time.get(url, 0)
        > time.time() - PREFLIGHT_H3_DOWNGRADE_TTL
    ):
        return True
    return False


def _set_h3_downgrade(url: str, reason: str) -> None:
    h3_downgrade_cache[url] = reason
    h3_downgrade_cache_time[url] = time.time()
    _persist_preflight_cache()


def _h2_downgrade_active(url: str) -> bool:
    entry = h2_downgrade_cache.get(url)
    if (
        entry
        and h2_downgrade_cache_time.get(url, 0)
        > time.time() - PREFLIGHT_H2_DOWNGRADE_TTL
    ):
        return True
    return False


def _set_h2_downgrade(url: str, reason: str) -> None:
    h2_downgrade_cache[url] = reason
    h2_downgrade_cache_time[url] = time.time()
    _persist_preflight_cache()


def _set_stream_fingerprint(url: str, fingerprint: dict) -> None:
    if not fingerprint:
        return
    stream_fingerprint_cache[url] = fingerprint
    stream_fingerprint_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_stream_fingerprint(url: str) -> dict | None:
    cached = stream_fingerprint_cache.get(url)
    if (
        cached
        and stream_fingerprint_cache_time.get(url, 0) > time.time() - 24 * 60 * 60
    ):
        return cached
    return None


def _rtsp_key(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.hostname:
        port = parsed.port or (322 if parsed.scheme.lower() == "rtsps" else 554)
        return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}:{port}"
    return None


def _rtsp_probe_cached(url: str) -> bool | None:
    key = _rtsp_key(url)
    if not key:
        return None
    if rtsp_probe_cache_time.get(key, 0) <= time.time() - PREFLIGHT_RTSP_PROBE_TTL:
        return None
    return rtsp_probe_cache.get(key)


def _set_rtsp_probe(url: str, value: bool) -> None:
    key = _rtsp_key(url)
    if not key:
        return
    rtsp_probe_cache[key] = value
    rtsp_probe_cache_time[key] = time.time()
    _persist_preflight_cache()


def _set_http_error(url: str, code: int) -> None:
    http_error_cache[url] = code
    http_error_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_http_error(url: str) -> int | None:
    code = http_error_cache.get(url)
    if code and http_error_cache_time.get(url, 0) > time.time() - 60 * 60:
        return code
    return None


def _set_auth_scheme(url: str, scheme: str | None, realm: str | None = None) -> None:
    if not scheme:
        return
    auth_scheme_cache[url] = scheme
    auth_scheme_cache_time[url] = time.time()
    if realm:
        auth_realm_cache[url] = realm
        auth_realm_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_auth_scheme(url: str) -> str | None:
    scheme = auth_scheme_cache.get(url)
    if scheme and auth_scheme_cache_time.get(url, 0) > time.time() - 60 * 60:
        return scheme
    return None


def _get_method_preference(url: str) -> str | None:
    key = _domain_key(url)
    if not key:
        return None
    pref = method_pref_cache.get(key)
    if pref and method_pref_cache_time.get(key, 0) > time.time() - 24 * 60 * 60:
        return pref
    return None


def _set_method_preference(url: str, method: str) -> None:
    key = _domain_key(url)
    if not key or not method:
        return
    method_pref_cache[key] = method
    method_pref_cache_time[key] = time.time()
    _persist_preflight_cache()


def _get_image_hash(url: str) -> str | None:
    cached = image_hash_cache.get(url)
    if cached and image_hash_cache_time.get(url, 0) > time.time() - 24 * 60 * 60:
        return cached
    return None


def _set_image_hash(url: str, digest: str) -> None:
    if not digest:
        return
    image_hash_cache[url] = digest
    image_hash_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_mjpeg_probe(url: str) -> bool | None:
    cached = mjpeg_probe_cache.get(url)
    if (
        cached is not None
        and mjpeg_probe_cache_time.get(url, 0) > time.time() - 60 * 60
    ):
        return cached
    return None


def _set_mjpeg_probe(url: str, value: bool) -> None:
    mjpeg_probe_cache[url] = value
    mjpeg_probe_cache_time[url] = time.time()
    _persist_preflight_cache()


def _set_latency(url: str, value: float) -> None:
    if value <= 0:
        return
    latency_cache[url] = value
    latency_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_latency(url: str) -> float | None:
    value = latency_cache.get(url)
    if value is not None and latency_cache_time.get(url, 0) > time.time() - 60 * 60:
        return value
    return None


def _set_cookie_wall(url: str) -> None:
    cookie_wall_cache[url] = True
    cookie_wall_cache_time[url] = time.time()
    _persist_preflight_cache()


def _has_cookie_wall(url: str) -> bool:
    if (
        cookie_wall_cache.get(url)
        and cookie_wall_cache_time.get(url, 0) > time.time() - 60 * 60
    ):
        return True
    return False


def _set_content_mismatch(url: str) -> None:
    content_mismatch_cache[url] = True
    content_mismatch_cache_time[url] = time.time()
    _persist_preflight_cache()


def _content_anomaly_active(url: str) -> bool:
    entry = content_anomaly_cache.get(url)
    if not entry:
        return False
    until = entry.get("until", 0)
    if until > time.time():
        return True
    return False


def _record_content_anomaly(url: str, reason: str) -> None:
    now = time.time()
    entry = content_anomaly_cache.setdefault(url, {"count": 0, "first": now})
    if now - entry.get("first", now) > PREFLIGHT_CONTENT_ANOMALY_WINDOW:
        entry["count"] = 0
        entry["first"] = now
    entry["count"] = entry.get("count", 0) + 1
    entry["last_reason"] = reason
    if entry["count"] >= PREFLIGHT_CONTENT_ANOMALY_THRESHOLD:
        entry["until"] = now + PREFLIGHT_CONTENT_ANOMALY_BACKOFF
        logging.info(
            "Content anomaly backoff for %s (%s): %ds",
            sanitize_url(url),
            reason,
            PREFLIGHT_CONTENT_ANOMALY_BACKOFF,
        )
    content_anomaly_cache[url] = entry
    content_anomaly_cache_time[url] = now
    _persist_preflight_cache()


def _record_partial_content(url: str, size: int, reason: str) -> None:
    now = time.time()
    entry = partial_content_cache.setdefault(url, {"count": 0, "first": now})
    if now - entry.get("first", now) > PREFLIGHT_PARTIAL_CONTENT_WINDOW:
        entry["count"] = 0
        entry["first"] = now
    entry["count"] = entry.get("count", 0) + 1
    entry["last_size"] = size
    entry["last_reason"] = reason
    if entry["count"] >= PREFLIGHT_PARTIAL_CONTENT_THRESHOLD:
        record_preflight_backoff(
            url,
            "partial_content",
            PREFLIGHT_PARTIAL_CONTENT_BACKOFF,
        )
        _record_tier_failure(url, TIER_HTTP, "partial_content")
    partial_content_cache[url] = entry
    partial_content_cache_time[url] = now
    _persist_preflight_cache()


def _record_cookie_churn(url: str, cookie_header: str | None) -> None:
    if not cookie_header:
        return
    now = time.time()
    entry = cookie_churn_cache.setdefault(url, {"count": 0, "first": now})
    if now - entry.get("first", now) > PREFLIGHT_COOKIE_CHURN_WINDOW:
        entry["count"] = 0
        entry["first"] = now
    entry["count"] = entry.get("count", 0) + 1
    entry["last"] = cookie_header[:256]
    if entry["count"] >= PREFLIGHT_COOKIE_CHURN_THRESHOLD:
        _set_cookie_wall(url)
        record_preflight_backoff(url, "cookie_churn", PREFLIGHT_COOKIE_CHURN_BACKOFF)
    cookie_churn_cache[url] = entry
    cookie_churn_cache_time[url] = now
    _persist_preflight_cache()


def _record_static_asset_stable(url: str) -> None:
    if not _url_looks_like_static_asset(url):
        return
    now = time.time()
    entry = static_asset_cache.setdefault(url, {"count": 0, "first": now})
    if now - entry.get("first", now) > PREFLIGHT_STATIC_ASSET_WINDOW:
        entry["count"] = 0
        entry["first"] = now
    entry["count"] = entry.get("count", 0) + 1
    if entry["count"] >= PREFLIGHT_STATIC_ASSET_THRESHOLD:
        record_preflight_backoff(
            url, "static_asset_stable", PREFLIGHT_STATIC_ASSET_BACKOFF
        )
    static_asset_cache[url] = entry
    static_asset_cache_time[url] = now
    _persist_preflight_cache()


def _html_stable_active(url: str) -> bool:
    entry = html_stable_cache.get(url)
    if not entry:
        return False
    until = entry.get("until", 0)
    if until > time.time():
        return True
    return False


def _record_html_stable(url: str) -> None:
    now = time.time()
    entry = html_stable_cache.setdefault(url, {"count": 0, "first": now})
    if now - entry.get("first", now) > PREFLIGHT_HTML_STABLE_WINDOW:
        entry["count"] = 0
        entry["first"] = now
    entry["count"] = entry.get("count", 0) + 1
    if entry["count"] >= PREFLIGHT_HTML_STABLE_THRESHOLD:
        entry["until"] = now + PREFLIGHT_HTML_STABLE_BACKOFF
        logging.info(
            "HTML stability backoff for %s: %ds",
            sanitize_url(url),
            PREFLIGHT_HTML_STABLE_BACKOFF,
        )
    html_stable_cache[url] = entry
    html_stable_cache_time[url] = now
    _persist_preflight_cache()


def _record_clock_skew(url: str, skew_seconds: float) -> None:
    clock_skew_cache[url] = skew_seconds
    clock_skew_cache_time[url] = time.time()
    _persist_preflight_cache()


def _sniff_media_type(payload: bytes) -> str | None:
    if not payload:
        return None
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a"):
        return "image/gif"
    if payload.startswith(b"%PDF-"):
        return "application/pdf"
    if payload.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if payload[4:8] == b"ftyp":
        return "video/mp4"
    return None


def _has_content_mismatch(url: str) -> bool:
    if (
        content_mismatch_cache.get(url)
        and content_mismatch_cache_time.get(url, 0) > time.time() - 60 * 60
    ):
        return True
    return False


def _set_codec_cache(url: str, codec: str | None) -> None:
    if not codec:
        return
    codec_cache[url] = codec
    codec_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_codec_cache(url: str) -> str | None:
    codec = codec_cache.get(url)
    if codec and codec_cache_time.get(url, 0) > time.time() - 24 * 60 * 60:
        return codec
    return None


def _codec_supported(codec: str | None) -> bool:
    if not codec:
        return True
    return codec.lower() in SUPPORTED_STREAM_CODECS


def _set_rtsp_auth_required(url: str) -> None:
    rtsp_auth_cache[url] = True
    rtsp_auth_cache_time[url] = time.time()
    _persist_preflight_cache()


def _rtsp_auth_required(url: str) -> bool:
    if (
        rtsp_auth_cache.get(url)
        and rtsp_auth_cache_time.get(url, 0) > time.time() - 60 * 60
    ):
        return True
    return False


def _set_rtsp_sdp(url: str, sdp: dict) -> None:
    if not sdp:
        return
    rtsp_sdp_cache[url] = sdp
    rtsp_sdp_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_rtsp_sdp(url: str) -> dict | None:
    sdp = rtsp_sdp_cache.get(url)
    if sdp and rtsp_sdp_cache_time.get(url, 0) > time.time() - 24 * 60 * 60:
        return sdp
    return None


def _set_rtsp_transport(url: str, transport: str) -> None:
    if not transport:
        return
    rtsp_transport_cache[url] = transport
    rtsp_transport_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_rtsp_transport(url: str) -> str | None:
    cached = rtsp_transport_cache.get(url)
    if cached and rtsp_transport_cache_time.get(url, 0) > time.time() - 24 * 60 * 60:
        return cached
    return None


def _set_rtsp_keepalive(url: str, ok: bool) -> None:
    rtsp_keepalive_cache[url] = ok
    rtsp_keepalive_cache_time[url] = time.time()
    _persist_preflight_cache()


def _rtsp_keepalive_ok(url: str) -> bool | None:
    cached = rtsp_keepalive_cache.get(url)
    if (
        cached is not None
        and rtsp_keepalive_cache_time.get(url, 0)
        > time.time() - PREFLIGHT_RTSP_KEEPALIVE_TTL
    ):
        return cached
    return None


def _set_rtsp_profile_url(url: str, profile_url: str) -> None:
    if not profile_url:
        return
    rtsp_profile_cache[url] = profile_url
    rtsp_profile_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_rtsp_profile_url(url: str) -> str | None:
    profile_url = rtsp_profile_cache.get(url)
    if profile_url and rtsp_profile_cache_time.get(url, 0) > time.time() - 24 * 60 * 60:
        return profile_url
    return None


def _rtsp_transport_candidates(url: str) -> list[str]:
    scheme = urlparse(url).scheme.lower()
    if scheme == "rtsps":
        # Secure RTSP over TLS is typically tunneled over TCP.
        return ["tcp"]
    preferred = _get_rtsp_transport(url) or "tcp"
    candidates = [preferred]
    for transport in ("tcp", "udp"):
        if transport not in candidates:
            candidates.append(transport)
    return candidates


def _build_rtsp_profile_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme.lower() != "rtsp":
        return []

    candidates = []
    path = parsed.path or ""
    query = parse_qs(parsed.query, keep_blank_values=True)

    match = re.search(r"/Streaming/Channels/(\d+)", path, re.I)
    if match:
        channel = int(match.group(1))
        if channel % 100 == 1:
            new_channel = channel + 1
            new_path = re.sub(
                r"/Streaming/Channels/\d+",
                f"/Streaming/Channels/{new_channel}",
                path,
                count=1,
                flags=re.I,
            )
            candidates.append(urlunparse(parsed._replace(path=new_path)))

    for token, replacement in (("stream1", "stream2"), ("stream0", "stream1")):
        if token in path.lower():
            new_path = re.sub(token, replacement, path, flags=re.I)
            candidates.append(urlunparse(parsed._replace(path=new_path)))

    if "subtype" in query and query["subtype"]:
        if query["subtype"][0] == "0":
            updated = dict(query)
            updated["subtype"] = ["1"]
            new_query = urlencode(updated, doseq=True)
            candidates.append(urlunparse(parsed._replace(query=new_query)))

    if "stream" in query and query["stream"]:
        if query["stream"][0] == "0":
            updated = dict(query)
            updated["stream"] = ["1"]
            new_query = urlencode(updated, doseq=True)
            candidates.append(urlunparse(parsed._replace(query=new_query)))

    seen = set()
    unique = []
    for candidate in candidates:
        if candidate not in seen and candidate != url:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _probe_rtsp_variant(url: str, timeout: int = 3) -> str | None:
    for candidate in _build_rtsp_profile_candidates(url):
        logging.debug(
            "RTSP profile candidate probe: %s -> %s",
            sanitize_url(url),
            sanitize_url(candidate),
        )
        if not _rtsp_options_probe(candidate, timeout):
            continue
        describe_ok, _ = _rtsp_describe_probe(candidate, timeout)
        if describe_ok:
            _set_rtsp_profile_url(url, candidate)
            logging.info(
                "RTSP profile selected: %s -> %s",
                sanitize_url(url),
                sanitize_url(candidate),
            )
            return candidate
    return None


def _rtsp_options_probe(url: str, timeout: int = 3) -> bool:
    cached = _rtsp_probe_cached(url)
    if cached is not None:
        return cached
    logging.debug("RTSP OPTIONS probe start: %s", sanitize_url(url))
    status, _, headers = _rtsp_request(url, "OPTIONS", timeout)
    logging.debug(
        "RTSP OPTIONS probe status=%s public=%s for %s",
        status,
        headers.get("Public"),
        sanitize_url(url),
    )
    if status == 401:
        _set_rtsp_auth_required(url)
        _set_rtsp_probe(url, False)
        return False
    if status == 200 and headers.get("Public"):
        _set_rtsp_probe(url, True)
        return True
    if status == 200:
        _set_rtsp_probe(url, True)
        return True
    _set_rtsp_probe(url, False)
    return False


def _rtsp_keepalive_probe(url: str, timeout: int = 2) -> bool:
    cached = _rtsp_keepalive_ok(url)
    if cached is not None:
        return cached
    logging.debug("RTSP keepalive probe start: %s", sanitize_url(url))
    status, _, _ = _rtsp_request(
        url, "GET_PARAMETER", timeout, headers_override={"Content-Length": "0"}
    )
    logging.debug("RTSP keepalive probe status=%s for %s", status, sanitize_url(url))
    if status == 401:
        _set_rtsp_auth_required(url)
        _set_rtsp_keepalive(url, False)
        return False
    ok = status in {200, 405, 501}
    _set_rtsp_keepalive(url, ok)
    return ok


def _rtsp_credentials(url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    if parsed.username and parsed.password:
        return unquote(parsed.username), unquote(parsed.password)
    return None, None


def _rtsp_url_with_credentials(
    url: str, username: str | None, password: str | None
) -> str:
    """Embed template auth into RTSP URLs so preflight and ffmpeg can use it."""
    if not username or not password:
        return url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        return url
    if parsed.username or not parsed.hostname:
        return url

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _rtsp_build_auth(
    method: str,
    uri: str,
    challenge: str | None,
    username: str | None,
    password: str | None,
) -> str | None:
    if not username or not password:
        return None
    if not challenge:
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        return f"Basic {token}"
    lower = challenge.lower()
    if "basic" in lower:
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        return f"Basic {token}"
    if "digest" not in lower:
        return None

    realm_match = re.search(r'realm="([^"]+)"', challenge, re.I)
    nonce_match = re.search(r'nonce="([^"]+)"', challenge, re.I)
    qop_match = re.search(r"qop=\"?([^\",]+)\"?", challenge, re.I)
    opaque_match = re.search(r'opaque="([^"]+)"', challenge, re.I)
    realm = realm_match.group(1) if realm_match else ""
    nonce = nonce_match.group(1) if nonce_match else ""
    qop = qop_match.group(1) if qop_match else None
    opaque = opaque_match.group(1) if opaque_match else None

    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    if qop:
        nc = "00000001"
        cnonce = secrets.token_hex(8)
        response = hashlib.md5(
            f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
        ).hexdigest()
    else:
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

    parts = [
        f'Digest username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'response="{response}"',
    ]
    if qop:
        parts.append(f"qop={qop}")
        parts.append("nc=00000001")
        parts.append(f'cnonce="{cnonce}"')
    if opaque:
        parts.append(f'opaque="{opaque}"')
    return ", ".join(parts)


def _read_rtsp_response(sock, deadline: float) -> tuple[int, str, dict[str, str]]:
    """Read one framed response, bounding time, headers and body allocation."""
    header_limit, body_limit = 64 * 1024, 1024 * 1024
    data = bytearray()

    def receive(size: int) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("RTSP response deadline exceeded")
        sock.settimeout(remaining)
        chunk = sock.recv(size)
        if not chunk:
            raise ValueError("Truncated RTSP response")
        return chunk

    while b"\r\n\r\n" not in data:
        if len(data) >= header_limit:
            raise ValueError("RTSP headers exceed limit")
        data.extend(receive(min(4096, header_limit - len(data))))
    head, body = bytes(data).split(b"\r\n\r\n", 1)
    lines = head.decode("ascii", errors="replace").split("\r\n")
    status_line = lines[0].split()
    if len(status_line) < 2 or status_line[0] != "RTSP/1.0":
        raise ValueError("Invalid RTSP status line")
    status = int(status_line[1])
    headers = requests.structures.CaseInsensitiveDict()
    for line in lines[1:]:
        if ":" not in line:
            raise ValueError("Invalid RTSP header")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if key.lower() == "content-length" and key in headers and headers[key] != value:
            raise ValueError("Conflicting RTSP content lengths")
        headers[key] = value
    length = int(headers.get("Content-Length", "0"))
    if length < 0 or length > body_limit:
        raise ValueError("Invalid RTSP body length")
    payload = bytearray(body[:length])
    while len(payload) < length:
        payload.extend(receive(min(4096, length - len(payload))))
    response = head + b"\r\n\r\n" + bytes(payload)
    return status, response.decode("ascii", errors="ignore"), headers


def _rtsp_request(
    url: str,
    method: str,
    timeout: int,
    accept: str | None = None,
    headers_override: dict[str, str] | None = None,
) -> tuple[int, str, dict[str, str]]:
    parsed = urlparse(url)
    if not parsed.hostname:
        return 0, "", {}
    port = parsed.port or (322 if parsed.scheme.lower() == "rtsps" else 554)
    username, password = _rtsp_credentials(url)
    uri = url
    headers = {
        "CSeq": "1",
        "User-Agent": "glimpser-preflight",
    }
    if accept:
        headers["Accept"] = accept
    if headers_override:
        headers.update(headers_override)

    def _serialize(headers_map: dict[str, str]) -> bytes:
        lines = [f"{method} {uri} RTSP/1.0"]
        lines += [f"{k}: {v}" for k, v in headers_map.items()]
        return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii", errors="ignore")

    try:
        sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
    except OSError:
        return 0, "", {}
    try:
        deadline = time.monotonic() + timeout
        sock.settimeout(timeout)
        if parsed.scheme.lower() == "rtsps":
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if not config.REQUEST_VERIFY_SSL:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            # Take ownership before the handshake, so failures close the TLS
            # socket in finally and never fall back to sending plaintext.
            sock = context.wrap_socket(
                sock, server_hostname=parsed.hostname, do_handshake_on_connect=False
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("RTSPS handshake deadline exceeded")
            sock.settimeout(remaining)
            sock.do_handshake()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("RTSPS handshake deadline exceeded")
            sock.settimeout(remaining)
        sock.sendall(_serialize(headers))
        status, response, header_map = _read_rtsp_response(sock, deadline)
        if status == 401 and username and password:
            auth_header = _rtsp_build_auth(
                method, uri, header_map.get("WWW-Authenticate"), username, password
            )
            if auth_header:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("RTSP authentication deadline exceeded")
                headers["CSeq"] = "2"
                headers["Authorization"] = auth_header
                sock.settimeout(remaining)
                sock.sendall(_serialize(headers))
                status, response, header_map = _read_rtsp_response(sock, deadline)
        return status, response, header_map
    except (OSError, TimeoutError, ValueError) as exc:
        logging.debug(
            "RTSP %s request failed for %s: %s",
            method,
            sanitize_url(url),
            exc,
        )
        return 0, "", {}
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _rtsp_describe_probe(url: str, timeout: int = 3) -> tuple[bool, str | None]:
    logging.debug("RTSP DESCRIBE probe start: %s", sanitize_url(url))
    status, response, headers = _rtsp_request(
        url, "DESCRIBE", timeout, accept="application/sdp"
    )
    logging.debug(
        "RTSP DESCRIBE probe status=%s content_type=%s for %s",
        status,
        headers.get("Content-Type"),
        sanitize_url(url),
    )
    if status == 401:
        _set_rtsp_auth_required(url)
        return False, None
    if status != 200:
        return False, None
    codec = None
    width = None
    height = None
    has_video = False
    current_media = None
    video_payloads: set[str] = set()
    for line in response.splitlines():
        if line.startswith("m=video"):
            # Some cameras announce recvonly SDP with media port 0 but still
            # provide playable video tracks. Presence of m=video is enough.
            has_video = True
            current_media = "video"
            parts = line.split()
            video_payloads = set(parts[3:]) if len(parts) > 3 else set()
            continue
        if line.startswith("m="):
            current_media = line[2:].split(" ", 1)[0].strip().lower()
            continue
        if line.startswith("a=rtpmap:"):
            if current_media != "video":
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                payload = parts[0].split(":", 1)[1].strip()
                if not video_payloads or payload in video_payloads:
                    codec = parts[1].split("/", 1)[0].strip().lower()
        if line.startswith("a=framesize:"):
            parts = line.split(" ", 1)
            if len(parts) == 2:
                dims = parts[1].strip()
                if "-" in dims:
                    w, h = dims.split("-", 1)
                elif "x" in dims:
                    w, h = dims.split("x", 1)
                else:
                    continue
                try:
                    width = int(w)
                    height = int(h)
                except ValueError:
                    pass
    if not has_video:
        logging.debug("RTSP DESCRIBE missing video media: %s", sanitize_url(url))
        return False, None
    if codec:
        _set_codec_cache(url, codec)
    _set_rtsp_sdp(
        url, {"codec": codec, "width": width, "height": height, "has_video": has_video}
    )
    if headers.get("Content-Type") == "application/sdp":
        return True, codec
    return True, codec


def _snapshot_key(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.hostname:
        return parsed.hostname.lower()
    return None


def _get_snapshot_probe(url: str) -> str | None:
    key = _snapshot_key(url)
    if not key:
        return None
    if snapshot_probe_cache_time.get(key, 0) <= time.time() - 60 * 60:
        return None
    entry = snapshot_probe_cache.get(key)
    if not entry:
        return None
    if entry.get("ok"):
        return entry.get("url")
    return None


def _set_snapshot_probe(url: str, snapshot_url: str | None) -> None:
    key = _snapshot_key(url)
    if not key:
        return
    snapshot_probe_cache[key] = {"ok": bool(snapshot_url), "url": snapshot_url}
    snapshot_probe_cache_time[key] = time.time()
    _persist_preflight_cache()


def _build_snapshot_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    if not parsed.hostname:
        return []
    host = parsed.hostname
    candidates = []
    ports = []
    if parsed.port and parsed.port not in (80, 443, 554):
        ports.append(parsed.port)
    hosts = [host] + [f"{host}:{p}" for p in ports]
    paths = [
        "/ISAPI/Streaming/channels/101/picture",
        "/Streaming/channels/101/picture",
        "/ISAPI/Streaming/channels/1/picture",
        "/snapshot.jpg",
        "/snapshot.cgi",
        "/cgi-bin/snapshot.cgi",
        "/cgi-bin/snap.jpg",
        "/axis-cgi/jpg/image.cgi",
        "/axis-cgi/jpg/image.jpg",
        "/axis-cgi/mjpg/video.cgi?resolution=640x360",
        "/image.jpg",
        "/jpg/image.jpg",
        "/SnapshotJPEG",
        "/snap.jpg",
        "/mjpg/video.mjpg",
        "/jpeg/snap.jpeg",
    ]
    for base in hosts:
        for scheme in ("http", "https"):
            for path in paths:
                candidates.append(f"{scheme}://{base}{path}")
    return candidates


def _probe_snapshot_url(
    url: str, username: str | None = None, password: str | None = None
) -> str | None:
    cached = _get_snapshot_probe(url)
    if cached is not None:
        return cached
    for candidate in _build_snapshot_candidates(url):
        ctype, _, preflight_ok, _ = get_content_type(
            candidate, False, username=username, password=password
        )
        if preflight_ok and is_image_url(candidate, ctype):
            _set_snapshot_probe(url, candidate)
            return candidate
    _set_snapshot_probe(url, None)
    return None


def _probe_mjpeg(
    url: str, username: str | None = None, password: str | None = None
) -> bool:
    cached = _get_mjpeg_probe(url)
    if cached is not None:
        return cached
    auth = get_preferred_auth(url, username, password)
    request_kwargs = dict(
        stream=True,
        timeout=5,
        verify=config.REQUEST_VERIFY_SSL,
        headers={"User-Agent": UA},
        auth=auth,
    )
    resp = None
    valid = False
    try:
        resp = http_session().get(url, **request_kwargs)
        if 200 <= resp.status_code < 300:
            # Use one iterator: sniffing with a separate iterator discards the
            # first bytes and can consume the only frame the camera sends.
            valid = _validate_mjpeg_frame(resp)
    except Exception:
        valid = False
    finally:
        if resp is not None:
            resp.close()
    _set_mjpeg_probe(url, valid)
    return valid


def _validate_mjpeg_frame(response) -> bool:
    """Find a JPEG start marker within a bounded amount of stream data."""
    remaining = 1024 * 1024
    deadline = time.monotonic() + 5
    previous = b""
    try:
        for chunk in response.iter_content(chunk_size=2048):
            # The request's socket timeout bounds idle reads; this budget is
            # checked between chunks and is not a hard whole-request deadline.
            if time.monotonic() >= deadline:
                return False
            if not chunk:
                continue
            chunk = chunk[:remaining]
            if b"\xff\xd8" in previous + chunk:
                return True
            remaining -= len(chunk)
            if remaining <= 0:
                return False
            # Network chunk boundaries need not align with JPEG markers.
            previous = chunk[-1:]
    except Exception:
        return False
    return False


def _parse_www_authenticate(header: str) -> tuple[str | None, str | None]:
    if not header:
        return None, None
    lower = header.lower()
    scheme = None
    if "digest" in lower:
        scheme = "digest"
    elif "basic" in lower:
        scheme = "basic"
    realm_match = re.search(r'realm="([^"]+)"', header, re.I)
    realm = realm_match.group(1) if realm_match else None
    return scheme, realm


def _cache_entry_valid(url: str, default_ttl: int = 60 * 60) -> bool:
    expiry = last_camera_header_expiry.get(url)
    now = time.time()
    if expiry is not None:
        if now < expiry:
            return True
        last_camera_header.pop(url, None)
        last_camera_header_time.pop(url, None)
        last_camera_header_expiry.pop(url, None)
        return False
    return last_camera_header_time.get(url, 0) > now - default_ttl


def _parse_cache_control(headers: dict) -> int | None:
    cache_control = headers.get("Cache-Control", "")
    if not cache_control:
        return None
    for token in cache_control.split(","):
        token = token.strip().lower()
        if token.startswith("s-maxage="):
            value = token.split("=", 1)[1]
        elif token.startswith("max-age="):
            value = token.split("=", 1)[1]
        else:
            continue
        try:
            return max(int(value), 0)
        except ValueError:
            return None
    return None


def _cache_ttl_from_headers(headers: dict) -> int | None:
    max_age = _parse_cache_control(headers)
    if max_age is not None:
        age_header = headers.get("Age")
        if age_header:
            try:
                age = max(int(age_header), 0)
                return max(max_age - age, 0)
            except ValueError:
                return max_age
        return max_age

    expires = headers.get("Expires")
    if expires:
        try:
            parsed = email.utils.parsedate_to_datetime(expires)
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=datetime.UTC)
                delta = (parsed - datetime.datetime.now(datetime.UTC)).total_seconds()
                return max(int(delta), 0)
        except Exception:
            return None
    return None


def _get_cached_redirect(url: str) -> str | None:
    cached = redirect_cache.get(url)
    if cached and redirect_cache_time.get(url, 0) > time.time() - 60 * 60:
        return cached
    return None


def _set_cached_redirect(url: str, value: str | None) -> None:
    if not value:
        return
    redirect_cache[url] = value
    redirect_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_redirect_pin(url: str) -> str | None:
    pinned = redirect_pin_cache.get(url)
    if (
        pinned
        and redirect_pin_cache_time.get(url, 0)
        > time.time() - PREFLIGHT_REDIRECT_PIN_TTL
    ):
        return pinned
    return None


def _set_redirect_pin(url: str, value: str | None) -> None:
    if not value:
        return
    redirect_pin_cache[url] = value
    redirect_pin_cache_time[url] = time.time()
    _persist_preflight_cache()


def _set_redirect_loop(url: str) -> None:
    redirect_loop_cache[url] = "redirect_loop"
    redirect_loop_cache_time[url] = time.time()
    _persist_preflight_cache()


def _set_redirect_chain(url: str) -> None:
    redirect_loop_cache[url] = "redirect_chain"
    redirect_loop_cache_time[url] = time.time()
    _persist_preflight_cache()


def _has_redirect_loop(url: str) -> bool:
    entry = redirect_loop_cache.get(url)
    if not entry:
        return False
    if redirect_loop_cache_time.get(url, 0) <= time.time() - 60 * 60:
        return False
    # Only treat explicit markers as "loop". Dict entries track redirect
    # fingerprints and should not hard-block future probes.
    return isinstance(entry, str) and entry in {"redirect_loop", "redirect_chain"}


def _is_redirect_loop(history, final_url: str, limit: int = 8) -> bool:
    if not history:
        return False

    # Only treat actual HTTP redirects as part of redirect-loop detection.
    # requests' auth handling can place 401 responses in resp.history, which
    # would otherwise be misclassified as a redirect loop.
    redirects = []
    for resp in history:
        code = getattr(resp, "status_code", None)
        if code in {301, 302, 303, 307, 308}:
            redirects.append(resp)

    if not redirects:
        return False

    if len(redirects) >= limit:
        return True

    seen = set()
    for resp in redirects:
        url = getattr(resp, "url", None)
        if not url:
            continue
        if url in seen:
            return True
        seen.add(url)

    if final_url in seen:
        return True

    return False


def _set_auth_hint(url: str) -> None:
    auth_hint_cache[url] = True
    auth_hint_cache_time[url] = time.time()
    _persist_preflight_cache()


def _get_auth_hint(url: str) -> bool:
    if (
        auth_hint_cache.get(url)
        and auth_hint_cache_time.get(url, 0) > time.time() - 60 * 60
    ):
        return True
    return False


def _preflight_dns_tls(url: str, timeout: int = 3) -> tuple[bool, str]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return True, "skip"

    hostname = parsed.hostname
    if not hostname:
        return False, "no_hostname"
    port = parsed.port or (443 if scheme == "https" else 80)
    key = f"{hostname}:{port}"

    cached = dns_cache.get(key)
    # Failures need a short retry window, not the hour-long healthy cache TTL.
    dns_ttl = PREFLIGHT_DNS_CACHE_TTL if cached else min(30, PREFLIGHT_DNS_CACHE_TTL)
    dns_fresh = (
        cached is not None and dns_cache_time.get(key, 0) > time.time() - dns_ttl
    )
    if dns_fresh and not cached:
        return False, "dns_failed"
    resolved_private = False
    if not dns_fresh:
        try:
            addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            for info in addrinfo:
                try:
                    sockaddr = info[4]
                    resolved_ip = ipaddress.ip_address(sockaddr[0])
                except (IndexError, TypeError, ValueError):
                    continue
                if (
                    resolved_ip.is_private
                    or resolved_ip.is_loopback
                    or resolved_ip.is_link_local
                ):
                    resolved_private = True
                    break
            dns_cache[key] = True
            dns_cache_time[key] = time.time()
        except Exception:
            dns_cache[key] = False
            dns_cache_time[key] = time.time()
            _persist_preflight_cache()
            return False, "dns_failed"
        _persist_preflight_cache()

    if scheme != "https":
        return True, "dns_ok"

    if not config.REQUEST_VERIFY_SSL and (
        _is_private_host(hostname) or _is_lan_target(hostname) or resolved_private
    ):
        # Private camera/dashboard assets often use local self-signed certs.
        # Match the downloader's configured SSL behavior instead of blocking
        # these sources during the lightweight TLS preflight.
        return True, "tls_skipped_private"

    if not config.REQUEST_VERIFY_SSL:
        # The request/downloader layer will not verify certificates in this
        # configuration. Keep preflight consistent so public cameras with
        # incomplete/self-signed chains are not rejected before download.
        return True, "tls_skipped_verify_disabled"

    cached_tls = tls_cache.get(key)
    if cached_tls is not None and tls_cache_time.get(key, 0) > time.time() - (
        PREFLIGHT_TLS_CACHE_TTL if cached_tls else min(30, PREFLIGHT_TLS_CACHE_TTL)
    ):
        return cached_tls, "tls_cache" if cached_tls else "tls_failed"

    try:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                alpn = tls_sock.selected_alpn_protocol()
        tls_cache[key] = True
        tls_cache_time[key] = time.time()
        _persist_preflight_cache()
        if alpn:
            _set_alpn(url, alpn)
            if alpn == "h2" and _h2_downgrade_active(url):
                return True, "tls_ok_h1"
            return True, f"tls_ok_{alpn}"
        return True, "tls_ok"
    except Exception:
        tls_cache[key] = False
        tls_cache_time[key] = time.time()
        _persist_preflight_cache()
        return False, "tls_failed"


def get_content_type(
    url, danger, stealth=False, username=None, password=None
) -> tuple[str, bool, bool, str]:
    """
    Determine the content type of the URL.

    This function determines content type with a tiny ranged GET probe,
    and caches the result for an hour to reduce unnecessary requests.

    Args:
        url (str): The URL to check.
        danger (bool): If True, skip content type checking.

    Returns:
        tuple[str, bool, bool, str]: The content type, modified flag,
        preflight status, and a preflight reason string.
    """
    # Check cache first
    if last_camera_header.get(url) and _cache_entry_valid(url):
        return last_camera_header.get(url), True, True, "cache"

    if "http" not in url or danger:
        return "", True, True, "skip"

    content_type = ""
    clean_url = sanitize_url(url)

    parsed = urlparse(url)
    if not is_system_online():
        if _is_private_host(parsed.hostname):
            logging.info(
                "System offline; continuing preflight for local URL %s",
                clean_url,
            )
        else:
            logging.warning(
                "System offline; skipping content type check for %s",
                clean_url,
            )
            return "", False, False, "offline"

    if parsed.scheme in {"http", "https"}:
        state = network_state()
        if not state.get("dns_ok", True) and not _is_private_host(parsed.hostname):
            logging.info("DNS offline; skipping external URL %s", clean_url)
            return "", False, False, "dns_offline"

    is_local_target = _is_private_host(parsed.hostname) or _is_lan_target(
        parsed.hostname
    )
    request_timeout_seconds = 5.0
    preflight_deadline = None
    if getattr(config, "LOW_CPU_MODE", False):
        budget_seconds = (
            PREFLIGHT_LOW_CPU_LOCAL_BUDGET_SECONDS
            if is_local_target
            else PREFLIGHT_LOW_CPU_WAN_BUDGET_SECONDS
        )
        budget_seconds = max(1, int(budget_seconds))
        preflight_deadline = time.monotonic() + float(budget_seconds)
        request_timeout_seconds = min(request_timeout_seconds, float(budget_seconds))

    def _next_preflight_timeout() -> float:
        if preflight_deadline is None:
            return request_timeout_seconds
        remaining = preflight_deadline - time.monotonic()
        if remaining <= 0:
            return 0.0
        return max(0.25, min(request_timeout_seconds, remaining))

    lua = UA
    if stealth:
        lua = random_user_agent()

    sess = http_session()
    modified = False
    content_type = ""
    preflight_ok = False
    preflight_reason = "request_failed"

    conditional_headers = {}
    cached_etag = etag_cache.get(url)
    cached_last_modified = last_modified_cache.get(url)
    if cached_etag:
        conditional_headers["If-None-Match"] = cached_etag
    if cached_last_modified:
        conditional_headers["If-Modified-Since"] = cached_last_modified

    accept_ranges = _get_accept_ranges(url)
    probe_url = _get_redirect_pin(url) or _get_cached_redirect(url) or url
    # Don't "upgrade" LAN hosts from http -> https just because we observed a
    # prior redirect. Many cameras expose only one of 80/443, and pinning to
    # https can cause repeated connection-refused failures (port 443) even when
    # the original http URL is correct.
    if parsed.scheme == "http" and _is_private_host(parsed.hostname):
        try:
            pinned_scheme = urlparse(probe_url).scheme.lower()
        except Exception:
            pinned_scheme = ""
        if pinned_scheme == "https":
            probe_url = url
    for verb in ("GET",):  # prefer a tiny ranged GET probe over HEAD
        try:
            attempt_timeout = _next_preflight_timeout()
            if attempt_timeout <= 0:
                return "", False, False, "preflight_budget_exceeded"
            # extra header only for the GET probe
            hdrs = {
                "User-Agent": lua,
                "Accept": "audio/*, application/octet-stream;q=0.9, */*;q=0.1",
            }
            if _h2_downgrade_active(url):
                hdrs["Connection"] = "close"
                hdrs["Accept-Encoding"] = "identity"
                hdrs["Cache-Control"] = "no-transform"
            if verb == "GET" and accept_ranges != "none":
                hdrs["Range"] = "bytes=0-2048"
            if conditional_headers:
                hdrs.update(conditional_headers)
            auth = get_preferred_auth(url, username, password)
            previous_max_redirects = getattr(sess, "max_redirects", None)
            try:
                if previous_max_redirects is not None:
                    sess.max_redirects = MAX_REDIRECTS
                start_time = time.time()
                resp = sess.request(
                    verb,
                    probe_url,
                    headers=hdrs,
                    auth=auth,
                    allow_redirects=True,
                    timeout=attempt_timeout,
                    stream=(verb == "GET"),
                )
                if resp.history and resp.cookies:
                    for entry in resp.history:
                        if entry.status_code in {
                            301,
                            302,
                            303,
                            307,
                            308,
                        } and entry.headers.get("Set-Cookie"):
                            _set_cookie_wall(url)
                            break
                if resp.headers.get("Set-Cookie"):
                    _record_cookie_churn(url, resp.headers.get("Set-Cookie"))
                _set_latency(url, time.time() - start_time)
            finally:
                if previous_max_redirects is not None:
                    sess.max_redirects = previous_max_redirects

            if resp.status_code == 416 and verb == "GET" and "Range" in hdrs:
                _set_accept_ranges(url, "none")
                resp.close()
                hdrs.pop("Range", None)
                try:
                    if previous_max_redirects is not None:
                        sess.max_redirects = MAX_REDIRECTS
                    start_time = time.time()
                    resp = sess.request(
                        verb,
                        probe_url,
                        headers=hdrs,
                        auth=auth,
                        allow_redirects=True,
                        timeout=_next_preflight_timeout() or attempt_timeout,
                        stream=(verb == "GET"),
                    )
                    if resp.history and resp.cookies:
                        for entry in resp.history:
                            if entry.status_code in {
                                301,
                                302,
                                303,
                                307,
                                308,
                            } and entry.headers.get("Set-Cookie"):
                                _set_cookie_wall(url)
                                break
                    if resp.headers.get("Set-Cookie"):
                        _record_cookie_churn(url, resp.headers.get("Set-Cookie"))
                    _set_latency(url, time.time() - start_time)
                finally:
                    if previous_max_redirects is not None:
                        sess.max_redirects = previous_max_redirects

            if resp.status_code == 401:
                scheme, realm = _parse_www_authenticate(
                    resp.headers.get("WWW-Authenticate", "")
                )
                if scheme:
                    _set_auth_scheme(url, scheme, realm)
                if not auth:
                    _set_auth_hint(url)
                    _set_domain_backoff(url, "http_401", PREFLIGHT_BACKOFF_DOMAIN_AUTH)
                    logging.info("Auth required for %s", clean_url)
                    return "", False, False, "auth_required"
                if scheme == "digest":
                    # Preserve explicit template credentials on the retry.
                    # Some cameras challenge the first probe even when we
                    # already know digest is required, and dropping the saved
                    # credentials here makes the preflight misclassify a live
                    # camera as auth_required.
                    auth = get_digest_auth(url, username, password)
                else:
                    auth = get_auth(url, username, password)
                try:
                    if previous_max_redirects is not None:
                        sess.max_redirects = MAX_REDIRECTS
                    start_time = time.time()
                    resp = sess.request(
                        verb,
                        probe_url,
                        headers=hdrs,
                        auth=auth,
                        allow_redirects=True,
                        timeout=_next_preflight_timeout() or attempt_timeout,
                        stream=(verb == "GET"),
                    )
                    if resp.history and resp.cookies:
                        for entry in resp.history:
                            if entry.status_code in {
                                301,
                                302,
                                303,
                                307,
                                308,
                            } and entry.headers.get("Set-Cookie"):
                                _set_cookie_wall(url)
                                break
                    _set_latency(url, time.time() - start_time)
                finally:
                    if previous_max_redirects is not None:
                        sess.max_redirects = previous_max_redirects

            if resp.status_code == 304:
                content_type = last_camera_header.get(url, "")
                modified = False
                preflight_ok = True
                preflight_reason = "not_modified"
                break
            if resp.status_code == 429:
                record_rate_limit(url, resp)
                resp.close()
                return "", False, False, "rate_limited"
            if resp.status_code == 503:
                _record_retry_after(url, resp, 300, reason="server_unavailable")
                resp.close()
                return "", False, False, "server_unavailable"
            if resp.status_code in {421, 426, 505}:
                _set_h3_downgrade(url, f"http_{resp.status_code}")
                _set_h2_downgrade(url, f"http_{resp.status_code}")
            if resp.status_code >= 400:
                if resp.status_code == 401 and not auth:
                    _set_auth_hint(url)
                    _set_domain_backoff(url, "http_401", PREFLIGHT_BACKOFF_DOMAIN_AUTH)
                    logging.info("Auth required for %s", clean_url)
                    return "", False, False, "auth_required"
                if resp.status_code in {403, 404, 410}:
                    if resp.status_code == 403:
                        _set_domain_backoff(
                            url, "http_403", PREFLIGHT_BACKOFF_DOMAIN_AUTH
                        )
                    else:
                        _set_domain_backoff(
                            url,
                            f"http_{resp.status_code}",
                            PREFLIGHT_BACKOFF_DOMAIN_NOT_FOUND,
                        )
                    _set_http_error(url, resp.status_code)
                if resp.status_code >= 500:
                    _record_retry_after(
                        url, resp, 300, reason=f"http_{resp.status_code}"
                    )
                logging.info(f"HTTP error {resp.status_code} for {clean_url}")
                set_cached_status_code(url, resp.status_code)
                return "", False, False, f"http_{resp.status_code}"

            history = resp.history if isinstance(resp.history, (list, tuple)) else []
            final_url = resp.url if isinstance(resp.url, str) else None
            redirects = [
                h
                for h in history
                if getattr(h, "status_code", None) in {301, 302, 303, 307, 308}
                and getattr(h, "url", None)
            ]
            if redirects and final_url:
                if len(redirects) >= MAX_REDIRECTS:
                    _set_redirect_chain(url)
                    return "", False, False, "redirects_exceeded"
                if _is_redirect_loop(redirects, final_url):
                    _set_redirect_loop(url)
                    return "", False, False, "redirect_loop"
                _set_cached_redirect(url, final_url)
                _set_redirect_pin(url, final_url)
                chain_urls = [h.url for h in redirects] + [final_url]
                fingerprint = " -> ".join(chain_urls)
                chain_entry = redirect_loop_cache.get(url)
                if (
                    chain_entry
                    and isinstance(chain_entry, dict)
                    and chain_entry.get("fingerprint") == fingerprint
                    and chain_entry.get("count", 0) + 1
                    >= REDIRECT_CHAIN_REPEAT_THRESHOLD
                ):
                    _set_redirect_chain(url)
                    return "", False, False, "redirect_chain_repeat"
                redirect_loop_cache[url] = {
                    "fingerprint": fingerprint,
                    "count": (chain_entry or {}).get("count", 0) + 1,
                }
                redirect_loop_cache_time[url] = time.time()
                _persist_preflight_cache()
            modified = check_if_modified(url, resp.headers)
            content_type = resp.headers.get("Content-Type", "").lower()
            if resp.status_code == 206 or resp.headers.get("Content-Range"):
                _set_accept_ranges(url, "bytes")
                if resp.raw and hasattr(resp.raw, "read"):
                    sample = resp.raw.read(PREFLIGHT_PARTIAL_CONTENT_MIN_BYTES)
                    if len(sample) < PREFLIGHT_PARTIAL_CONTENT_MIN_BYTES:
                        _record_partial_content(url, len(sample), "tiny_partial")
            if content_type.startswith("text/html") and (
                _url_looks_like_image(url) or _url_looks_like_pdf(url)
            ):
                _set_auth_hint(url)
                _set_content_mismatch(url)
                _record_content_anomaly(url, "html_mismatch")
                return "", False, False, "html_login"
            if resp.headers.get("Date"):
                try:
                    parsed = email.utils.parsedate_to_datetime(resp.headers["Date"])
                    if parsed is not None:
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=datetime.UTC)
                        skew = abs(
                            (
                                parsed - datetime.datetime.now(datetime.UTC)
                            ).total_seconds()
                        )
                        if skew > PREFLIGHT_CLOCK_SKEW_SECONDS:
                            _record_clock_skew(url, skew)
                            logging.info(
                                "Clock skew detected for %s: %ds",
                                clean_url,
                                int(skew),
                            )
                except Exception:
                    pass
            accept_ranges_header = resp.headers.get("Accept-Ranges", "").lower()
            if accept_ranges_header:
                _set_accept_ranges(url, accept_ranges_header)
            alt_svc_header = resp.headers.get("Alt-Svc")
            if alt_svc_header:
                _set_alt_svc(url, alt_svc_header)
            content_length_header = resp.headers.get("Content-Length")
            if content_length_header:
                try:
                    _set_content_length(url, int(content_length_header))
                except ValueError:
                    pass
            if (
                (
                    content_type.startswith("application/octet-stream")
                    or content_type.startswith("binary/")
                    or content_type == ""
                )
                and resp.raw
                and hasattr(resp.raw, "read")
            ):
                payload = resp.raw.read(PREFLIGHT_SNIFF_BYTES)
                sniffed = _sniff_media_type(payload)
                if sniffed and not content_type:
                    content_type = sniffed
                elif sniffed and content_type and sniffed not in content_type:
                    _record_content_anomaly(url, f"sniff_{sniffed}")
            preflight_ok = True
            preflight_reason = "ok"
            break  # success → stop loop
        except requests.exceptions.TooManyRedirects:
            _set_redirect_loop(url)
            return "", False, False, "redirects_exceeded"
        except Exception as e:
            if "http/3" in str(e).lower() or "h3" in str(e).lower():
                _set_h3_downgrade(url, "exception_h3")
            if "http/2" in str(e).lower() or "h2" in str(e).lower():
                _set_h2_downgrade(url, "exception_h2")
            logging.info(f"{verb} {clean_url} failed: {e}")

    """
    modified = True
    for method in methods:
        try:
            headers = {"user-agent": lua}
            if method == requests.get:
                headers["Range"] = "bytes=0-1024"

            auth = get_auth(url, username, password)
            response = method(
                url,
                stream=True,
                timeout=5,
                verify=config.REQUEST_VERIFY_SSL,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )

            if response.status_code == 401 and auth:
                auth = get_digest_auth(url)
                response = method(
                    url,
                    timeout=5,
                    verify=config.REQUEST_VERIFY_SSL,
                    headers=headers,
                    auth=auth,
                    allow_redirects=True,
                )

            if response.status_code >= 400:
                logging.info(f"HTTP error {response.status_code} for {clean_url}")
                set_cached_status_code(url, response.status_code)
                return "", False

            modified = check_if_modified(url, response.headers)

            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            break  # Exit the loop if successful
        except Exception as e:
            logging.info(f"Error {method.__name__.upper()} {clean_url}: {e}")
    """

    # Cache the result
    if content_type:
        last_camera_header[url] = content_type
        last_camera_header_time[url] = time.time()
        ttl = _cache_ttl_from_headers(resp.headers)
        if ttl is not None:
            last_camera_header_expiry[url] = time.time() + ttl
        _persist_preflight_cache()

    return content_type, modified, preflight_ok, preflight_reason


def get_auth(url, username=None, password=None):
    """Return :class:`HTTPBasicAuth` if credentials are available."""
    parsed = urlparse(url)
    if parsed.username is not None and parsed.password is not None:
        return requests.auth.HTTPBasicAuth(
            unquote(parsed.username), unquote(parsed.password)
        )
    if username and password:
        return requests.auth.HTTPBasicAuth(username, password)
    return None


def get_digest_auth(url, username=None, password=None):
    """Return :class:`HTTPDigestAuth` if credentials are available."""
    parsed = urlparse(url)
    if parsed.username is not None and parsed.password is not None:
        return requests.auth.HTTPDigestAuth(
            unquote(parsed.username), unquote(parsed.password)
        )
    if username and password:
        return requests.auth.HTTPDigestAuth(username, password)
    return None


def get_preferred_auth(url, username=None, password=None):
    scheme = _get_auth_scheme(url)
    if scheme == "digest":
        return get_digest_auth(url, username, password)
    return get_auth(url, username, password)


def is_image_url(url, content_type):
    """Check if the URL is likely to be an image."""
    image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".gif", "/picture"]
    return (
        any(ext in url.lower() for ext in image_extensions) or "image/" in content_type
    )


def _url_looks_like_image(url: str) -> bool:
    image_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tif",
        ".gif",
        ".webp",
    ]
    url_lower = url.lower()
    return (
        any(url_lower.endswith(ext) for ext in image_extensions)
        or "snapshot" in url_lower
    )


def _url_looks_like_pdf(url: str) -> bool:
    url_lower = url.lower()
    return url_lower.endswith(".pdf") or "/pdf" in url_lower


def _url_looks_like_static_asset(url: str) -> bool:
    if _url_looks_like_image(url) or _url_looks_like_pdf(url):
        return True
    path = urlparse(url).path.lower()
    return path.endswith(
        (
            ".svg",
            ".css",
            ".js",
            ".woff",
            ".woff2",
            ".ttf",
            ".otf",
            ".ico",
        )
    )


def is_pdf_url(url, content_type):
    """Check if the URL is likely to be a PDF."""
    return ".pdf" in url.lower() or "/pdf" in content_type


def is_video_stream_url(url, content_type):
    """Check if the URL is likely to be a video stream."""
    video_indicators = [
        ".mjpg",
        ".mp4",
        ".gif",
        ".webp",
        "rtsp://",
        "rtsps://",
        ".m3u8",
        ":5004/",
    ]
    return (
        any(ind in url.lower() for ind in video_indicators) or "video/" in content_type
    )


def _ffmpeg_error_suggests_hwaccel_failure(stderr_text: str) -> bool:
    """Return whether ffmpeg failed before decode because HW accel is unavailable."""

    lower = (stderr_text or "").lower()
    return any(
        marker in lower
        for marker in (
            "cannot load libcuda",
            "could not dynamically load cuda",
            "device creation failed",
            "no device available for decoder",
            "no device availab",
        )
    )


def _ffmpeg_command_without_hwaccel(command: list[str]) -> list[str]:
    """Remove ``-hwaccel <value>`` from an ffmpeg command."""

    stripped: list[str] = []
    skip_next = False
    for value in command:
        if skip_next:
            skip_next = False
            continue
        if value == "-hwaccel":
            skip_next = True
            continue
        stripped.append(value)
    return stripped


def _decode_json_escaped_url(raw_value: str | None) -> str:
    """Decode JSON-escaped URL fragments embedded in HTML pages."""

    if not raw_value:
        return ""
    try:
        return json.loads(f'"{raw_value}"')
    except Exception:
        return (
            raw_value.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&")
        )


def _earthcam_extract_stream_url(
    page_url: str, timeout: int = 30, proxy: str | None = None
) -> str | None:
    """Return an embedded HLS stream URL from an EarthCam page when available.

    Many EarthCam pages wrap a real HLS playlist inside otherwise heavy HTML.
    Extracting that stream lets Glimpser use ffmpeg directly instead of paying
    the cost of a browser render for every still capture.
    """

    if not re.findall(
        r"^https?://((www\.)?earthcam\.com|myearthcam\.com)/",
        page_url,
        flags=re.I,
    ):
        return None

    request_kwargs = {
        "timeout": (timeout, timeout * 3),
        "verify": config.REQUEST_VERIFY_SSL,
        "headers": {"User-Agent": UA},
        "allow_redirects": True,
    }
    normalized_proxy = validate_proxy(proxy)
    if normalized_proxy:
        request_kwargs["proxies"] = {
            "http": normalized_proxy,
            "https": normalized_proxy,
        }

    try:
        resp = http_session().get(page_url, **request_kwargs)
    except Exception:
        return None

    try:
        if not resp.ok:
            return None
        body = resp.text or ""
    finally:
        resp.close()

    direct_match = re.search(r'"stream"\s*:\s*"([^"]+\.m3u8[^"]*)"', body, re.I)
    if direct_match:
        return _decode_json_escaped_url(direct_match.group(1))

    domain_match = re.search(
        r'"html5_streamingdomain"\s*:\s*"([^"]+)"',
        body,
        re.I,
    )
    path_match = re.search(
        r'"html5_streampath"\s*:\s*"([^"]+\.m3u8[^"]*)"',
        body,
        re.I,
    )
    if domain_match and path_match:
        stream_domain = _decode_json_escaped_url(domain_match.group(1)).rstrip("/")
        stream_path = _decode_json_escaped_url(path_match.group(1))
        if stream_domain and stream_path:
            if not stream_path.startswith("/"):
                stream_path = f"/{stream_path}"
            return f"{stream_domain}{stream_path}"
    return None


def should_use_lightweight_browser(
    url,
    dedicated_selector,
    popup_xpath,
    headless,
    stealth,
    browser,
    danger,
    name=None,
):
    """Determine if a lightweight browser should be used for capture."""

    requires_rich_browser = bool(
        _browser_capture_profile(url, name).get("prefer_rich_graphics")
    )
    return (
        re.findall(r"^https?://", url, flags=re.I)
        and dedicated_selector in [None, ""]
        and popup_xpath in [None, ""]
        and not stealth
        and not browser
        and not headless
        and not requires_rich_browser
        and not is_enhanced(url)
        and not danger
    )


def should_use_phantom_browser(
    url,
    dedicated_selector,
    popup_xpath,
    headless,
    stealth,
    browser,
    danger,
    name=None,
):
    """Determine if PhantomJS should be used for capture.

    PhantomJS is a best-effort renderer for simple, static pages. It is not
    reliable for modern JS-heavy sites and should not be used when the template
    is explicitly requesting a real browser workflow (headless/stealth) or when
    XPath-based cropping/overlay removal is configured.
    """
    requires_rich_browser = bool(
        _browser_capture_profile(url, name).get("prefer_rich_graphics")
    )
    return (
        re.findall(r"^https?://", url, flags=re.I)
        and dedicated_selector in [None, ""]
        and popup_xpath in [None, ""]
        and not headless
        and not stealth
        and not browser
        and not requires_rich_browser
        and not is_enhanced(url)
        and not danger
    )


# The rest of the functions (download_image, download_pdf, capture_frame_from_stream,
# capture_frame_with_ytdlp, capture_screenshot_and_har_light, capture_screenshot_and_har)
# should be implemented as before, with appropriate error handling and logging.


def capture_frame_with_ytdlp(
    url, output_path, name="unknown", invert=False, stabilize_mode="off"
):
    """
    Use yt-dlp to get the video URL, then ffmpeg to capture a single frame from that video.
    """
    if not _check_ffmpeg():
        return False

    if (
        lurl_cache.get(url, "none") != "good"
        and time.time() - lurl_cache_time.get(url, 0) < 3600
    ):  # try every 1 hour no matter what??
        # don't keep retrying on known bad
        logging.debug("skipping %s %s", lurl_cache[url], sanitize_url(url))
        return False

    lsuccess = False
    try:
        lurl_cache_time[url] = time.time()
        status, video_url = _resolve_ytdlp_video_url(url)
        lurl_cache[url] = status
        if video_url is None:
            return False

        # Validate the video_url to ensure it is a legitimate URL
        parsed_url = urlparse(video_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logging.error(f"Invalid video URL: {video_url}")
            return False

        # 2) Use ffmpeg to capture a single frame
        ffmpeg_command = [
            FFMPEG_PATH,
            "-analyzeduration",
            "20M",
            "-probesize",
            "20M",
            "-ec",
            "15",
            "-i",
            video_url,
            "-sn",
            "-an",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "rgb24",
            "-frames:v",
            "1",
            "-fflags",
            "+igndts+ignidx+genpts+fastseek+discardcorrupt",
            "-q:v",
            "0",
            "-f",
            "image2",
            "-y",
            output_path,
        ]
        subprocess.run(
            ffmpeg_command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CAPTURE_TIMEOUT,
        )

        # 3) Check output; add timestamp
        if os.path.exists(output_path) and _is_valid_png(output_path):
            with Image.open(output_path) as image:
                reject_reason = _captured_frame_rejection_reason(image)
                if reject_reason is not None:
                    logging.warning(
                        "[%s] Rejecting yt-dlp frame due to %s pattern: %s",
                        name,
                        reject_reason,
                        sanitize_url(url),
                    )
                    record_preflight_backoff(
                        url,
                        f"{reject_reason}_capture",
                        PREFLIGHT_BACKOFF_BROWSER_FAIL,
                    )
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                    return False
                image = _postprocess_still_image(
                    image,
                    output_path,
                    name,
                    stabilize_mode=stabilize_mode,
                )
                image.save(
                    output_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL
                )
            add_timestamp(output_path, name=name, invert=invert)
            logging.debug(
                f"Successfully captured frame with ytdlp+ffmpeg: {sanitize_url(url)}"
            )
            lsuccess = True

        return lsuccess

    except Exception as e:
        logging.error(f"Error capturing frame with yt-dlp and ffmpeg: {e}")
        return False

    finally:
        # If partial file was created but we didn't fully succeed, remove it
        if not lsuccess and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass


def _classify_ytdlp_failure(stderr_text: str) -> str:
    """Return the cache status that best matches a yt-dlp failure message."""

    if re.findall(r"(?:vailable|found|404)", stderr_text.lower()):
        return "offline"
    return "bad"


def _extract_direct_video_url(info: dict | None) -> str | None:
    """Extract the most useful direct stream URL from a yt-dlp info dict."""

    if not info:
        return None

    entries = info.get("entries") or []
    for entry in entries:
        candidate = _extract_direct_video_url(entry)
        if candidate:
            return candidate

    requested_formats = info.get("requested_formats") or []
    for fmt in requested_formats:
        candidate = fmt.get("url")
        if candidate:
            return candidate

    candidate = info.get("url")
    if candidate:
        return candidate

    formats = info.get("formats") or []
    for fmt in reversed(formats):
        candidate = fmt.get("url")
        if candidate:
            return candidate

    return None


def _resolve_ytdlp_video_url(url: str) -> tuple[str, str | None]:
    """Resolve *url* to a direct stream URL via yt-dlp CLI or module fallback."""

    ytdlp_binary = shutil.which("yt-dlp")
    if ytdlp_binary is not None:
        if PREFLIGHT_YTDLP_SIMULATE:
            simulate_cmd = [
                ytdlp_binary,
                "--simulate",
                "--skip-download",
                "--no-warnings",
                "--quiet",
                "--",
                url,
            ]
            simulate = subprocess.run(
                simulate_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=min(CAPTURE_TIMEOUT, 10),
                check=False,
            )
            if simulate.returncode != 0:
                return (
                    _classify_ytdlp_failure(simulate.stderr.decode("utf-8")),
                    None,
                )

        ytdlp_command = [
            ytdlp_binary,
            "--get-url",
            "--",
            url,
        ]
        result = subprocess.run(
            ytdlp_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CAPTURE_TIMEOUT,
            check=False,
        )
        if result.returncode == 0:
            return "good", result.stdout.decode().strip()

        logging.warning(
            "yt-dlp CLI failed for %s; falling back to Python module",
            sanitize_url(url),
        )

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "best",
    }
    try:
        # The module fallback avoids PATH issues on hosts where yt_dlp is
        # installed into the app environment but the `yt-dlp` executable is not.
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        direct_url = _extract_direct_video_url(info)
        if direct_url:
            return "good", direct_url
        logging.error("yt-dlp module did not yield a direct video URL for %s", url)
        return "bad", None
    except Exception as exc:
        logging.error("yt-dlp module failed for %s: %s", sanitize_url(url), exc)
        return _classify_ytdlp_failure(str(exc)), None


def _cap_probe_value(value: str, ceiling: int) -> str:
    """Bound a numeric ffmpeg probe setting while preserving smaller overrides."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmMgG]?)", str(value).strip())
    if not match:
        return str(value)
    amount = float(match[1]) * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9}[match[2].lower()]
    return str(ceiling) if amount > ceiling or amount == 0 else str(value)


def _publish_stream_frame(
    frame_path: str,
    output_path: str,
    name: str,
    *,
    invert: bool,
    stabilize_mode: str,
) -> None:
    """Finish a frame privately, then atomically replace the published image."""
    # Keep the stage on the destination filesystem so replace stays atomic even
    # when the burst directory is on a separate /tmp mount. Reference-dependent
    # processing still uses the real destination to find stabilization history.
    with tempfile.NamedTemporaryFile(
        prefix=".glimpser-stream-",
        suffix=".png",
        dir=os.path.dirname(os.path.abspath(output_path)),
        delete=False,
    ) as stage:
        stage_path = stage.name
    try:
        with Image.open(frame_path) as source:
            image = _postprocess_still_image(
                source, output_path, name, stabilize_mode=stabilize_mode
            )
            try:
                image.save(
                    stage_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL
                )
            finally:
                if image is not source:
                    image.close()
        add_timestamp(stage_path, name=name, invert=invert)
        if not _is_valid_png(stage_path):
            raise ValueError("Processed stream frame is not a readable PNG")
        os.replace(stage_path, output_path)
    finally:
        try:
            os.unlink(stage_path)
        except FileNotFoundError:
            pass


def capture_frame_from_stream(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    stealth=False,
    stabilize_mode="off",
    stream_burst_frames=None,
    stream_burst_span_ms=None,
):
    """Capture a short live-stream burst and keep the best still frame."""
    if not _check_ffmpeg():
        return False

    scheme = urlparse(url).scheme.lower()
    is_sdm_rtsps = scheme == "rtsps" and "sdm_live_stream" in url.lower()
    is_hdhomerun_stream = _is_hdhomerun_like_stream_url(url)
    if scheme in {"rtsp", "rtsps"}:
        # RTSP templates often need more than the generic HTTP preflight cap,
        # especially when the first decodable keyframe arrives late.
        probe_timeout = max(timeout, STREAM_PROBE_TIMEOUT, 3)
    else:
        probe_timeout = max(min(timeout, STREAM_PROBE_TIMEOUT), 3)
    if scheme == "rtsps":
        probe_timeout = max(probe_timeout, 20)

    ffprobe_ok = (
        True
        # This camera's extra probe destabilizes the encoder. The direct burst
        # is still checked for valid PNGs and repeated-row decoder smears.
        if is_sdm_rtsps
        or is_hdhomerun_stream
        or name in capture_policy.CAPTURE_POLICY.get("slow_rtsp_cameras", [])
        else _probe_stream_with_ffprobe(url, probe_timeout, name)
    )
    null_probe_ok = False
    if (
        PREFLIGHT_FFMPEG_NULL_PROBE
        and not ffprobe_ok
        and not is_sdm_rtsps
        and not is_hdhomerun_stream
    ):
        # The capture itself validates decoded PNGs. Opening a second decoder
        # after successful metadata inspection adds latency and encoder load.
        null_probe_ok = _ffmpeg_null_probe(url, probe_timeout, name, stealth)

    if not ffprobe_ok and not null_probe_ok:
        if scheme == "rtsps":
            # Google SDM often returns short-lived `rtsps://` URLs that can be
            # slow to answer preflight probes. Continue to direct capture so
            # we do not falsely mark cameras unavailable on probe timeout.
            logging.info(
                "Stream preflight timed out for %s; attempting direct capture",
                sanitize_url(url),
            )
        else:
            record_preflight_backoff(
                url, "stream_probe_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
            )
            return False

    if ffprobe_ok is False and null_probe_ok is True:
        logging.info(
            "Stream preflight: ffprobe failed but ffmpeg probe succeeded for %s",
            sanitize_url(url),
        )

    clean_url = sanitize_url(url)
    rejected_capture_reason = None
    timeout = max(timeout, 5)
    if is_hdhomerun_stream:
        # Give tuner-backed streams extra startup room before declaring failure.
        timeout = max(timeout, 20)

    # Concurrent captures must never clear one another's burst frames.
    with tempfile.TemporaryDirectory(prefix="glimpser_stream_") as tmpdirname:
        transports = [None]
        if scheme in {"rtsp", "rtsps"}:
            # TCP delivered clean frames for configured slow cameras in isolated probes.
            transports = (
                ["tcp"] * 3
                if name in capture_policy.CAPTURE_POLICY.get("slow_rtsp_cameras", [])
                else _rtsp_transport_candidates(url)
            )
        per_attempt_timeout = max(5, int(timeout / max(len(transports), 1)))
        if scheme in {"rtsp", "rtsps"}:
            # High-resolution RTSP cameras can take longer than half the
            # template timeout to deliver the first decodable keyframe.
            # Keep the template timeout as the baseline per transport instead
            # of prematurely rejecting healthy streams after only a few seconds.
            per_attempt_timeout = max(per_attempt_timeout, min(max(timeout, 10), 20))
        if scheme == "rtsps":
            per_attempt_timeout = max(per_attempt_timeout, 12)

        for transport in transports:
            # Capture multiple frames into the temporary directory
            temp_output_pattern = os.path.join(tmpdirname, "frame_%03d.png")
            for entry in os.listdir(tmpdirname):
                try:
                    os.remove(os.path.join(tmpdirname, entry))
                except OSError:
                    pass
            if transport:
                logging.debug(
                    "ffmpeg RTSP transport=%s for %s", transport, sanitize_url(url)
                )
            command = [
                FFMPEG_PATH,  # Use the configurable FFMPEG_PATH
                "-hide_banner",
                "-nostdin",
            ]
            if (
                FFMPEG_HWACCEL
                and FFMPEG_HWACCEL.lower() != "false"
                and not is_hdhomerun_stream
            ):
                command.extend(["-hwaccel", FFMPEG_HWACCEL])

            lua = UA
            if stealth:
                chrome_path = get_chrome_path()
                cv = get_chrome_version(chrome_path)
                lua = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36"
                    % cv
                )

            probe_size = PROBE_SIZE_DEFAULT
            analyze_duration = ANALYZE_DURATION_DEFAULT
            if scheme in {"http", "https"}:
                if not is_hdhomerun_stream:
                    parsed_url = urlparse(url)
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

                    command.extend(["-headers", "User-Agent: %s\r\n" % lua])
                    command.extend(["-headers", f"referer: {base_url}\r\n"])
                    command.extend(["-headers", f"origin: {base_url}\r\n"])
                    command.extend(["-seekable", "0"])
                # command.extend(['-timeout', str(CAPTURE_TIMEOUT-1)])  # not sure why, but this causes us a lot of issues, dont set a timetout
                probe_size = PROBE_SIZE_DEFAULT
                analyze_duration = ANALYZE_DURATION_DEFAULT
                if is_hdhomerun_stream:
                    probe_size = PROBE_SIZE_OTHER
                    analyze_duration = ANALYZE_DURATION_OTHER
            elif scheme in {"rtsp", "rtsps"}:
                if transport:
                    command.extend(["-rtsp_transport", transport])
                probe_size = PROBE_SIZE_RTSP
                analyze_duration = ANALYZE_DURATION_RTSP
                if "/streaming/" in url.lower():  # a little bit of a hack
                    command.extend(["-c:v", "h264"])
                    command.extend(["-r", "1"])
                    probe_size = PROBE_SIZE_OTHER
                    analyze_duration = ANALYZE_DURATION_OTHER
            else:
                probe_size = PROBE_SIZE_OTHER
                analyze_duration = ANALYZE_DURATION_OTHER

            if scheme in {"rtsp", "rtsps"}:
                # Stream inspection must leave time for decoder warmup and the
                # burst. A 20-second analysis budget consumed the entire capture
                # deadline on healthy low-FPS cameras such as Backyard.
                analyze_duration = _cap_probe_value(
                    analyze_duration, int(min(3, per_attempt_timeout / 4) * 1_000_000)
                )
                probe_size = _cap_probe_value(probe_size, 2_000_000)

            # Use configured values within the capture's inspection budget.
            command.extend(["-analyzeduration", analyze_duration])
            command.extend(["-probesize", probe_size])
            frames_to_capture = _normalize_stream_burst_frames(
                stream_burst_frames,
                default=NUM_FRAMES,
                is_hdhomerun_stream=is_hdhomerun_stream,
            )
            burst_span_ms = _normalize_stream_burst_span_ms(stream_burst_span_ms)
            if scheme in {"rtsp", "rtsps"}:
                frames_to_capture, burst_span_ms = _apply_low_fps_rtsp_burst_cap(
                    url, frames_to_capture, burst_span_ms
                )
            # Some RTSP encoders need reference frames even around keyframes.
            # Keyframe-only decoding produced long vertical smears on slow encoders.
            is_rtsp_stream = scheme in {"rtsp", "rtsps"}
            pre_input_args = (
                []
                if is_hdhomerun_stream or is_rtsp_stream
                else ["-skip_frame", "nokey"]
            )
            # Configured slow cameras need a longer decoder warmup to avoid repeated-row smears.
            # Keep the validated decoder warmup for opted-in encoders.
            warmup_seconds = (
                12
                if name in capture_policy.CAPTURE_POLICY.get("slow_rtsp_cameras", [])
                else 3
            )
            warmup_args = ["-ss", str(warmup_seconds)] if is_rtsp_stream else []
            movflags_args = [] if is_hdhomerun_stream else ["-movflags", "+faststart"]
            output_filter_args = []
            if burst_span_ms > 0 and frames_to_capture > 1:
                span_seconds = max(burst_span_ms / 1000.0, 0.1)
                burst_fps = max(frames_to_capture / span_seconds, 0.5)
                output_filter_args = ["-vf", f"fps={burst_fps:.3f}"]
            command.extend(
                [
                    "-use_wallclock_as_timestamps",
                    "1",
                    #'-ec', '15',
                    "-threads",
                    "1",
                    "-sn",
                    "-an",
                    *pre_input_args,
                    #'-err_detect','aggressive',
                    "-i",
                    url,  # Input stream URL
                    *warmup_args,
                    *movflags_args,
                    *output_filter_args,
                    "-pix_fmt",
                    "rgb24",
                    "-frames:v",
                    str(frames_to_capture),  # Capture burst and keep last frame
                    "-fflags",
                    "+igndts+ignidx+genpts+fastseek+discardcorrupt",
                    "-q:v",
                    "0",  # Output quality (lower is better)
                    #'-b:v', '50000000',               # Output quality (lower is better)
                    "-f",
                    "image2",  # Force image2 muxer
                    temp_output_pattern,  # Temporary output file pattern
                ]
            )

            if (
                name in capture_policy.CAPTURE_POLICY.get("slow_rtsp_cameras", [])
                and scheme == "rtsp"
            ):
                # The minimal software-decoded TCP burst was clean in multiple
                # trials; the generic command was intermittent.
                command = [
                    FFMPEG_PATH,
                    "-hide_banner",
                    "-nostdin",
                    "-rtsp_transport",
                    "tcp",
                    "-i",
                    url,
                    "-ss",
                    "12",
                    "-pix_fmt",
                    "rgb24",
                    "-frames:v",
                    "3",
                    "-f",
                    "image2",
                    temp_output_pattern,
                ]

            attempt_deadline = time.monotonic() + per_attempt_timeout
            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=per_attempt_timeout,
                )
            except subprocess.TimeoutExpired:
                logging.error(
                    (
                        "ffmpeg timed out for %s after %ss "
                        "(transport=%s hwaccel=%s frames=%s span_ms=%s "
                        "filter=%s skip_nokey=%s analyzeduration=%s probesize=%s)"
                    ),
                    clean_url,
                    per_attempt_timeout,
                    transport or "default",
                    FFMPEG_HWACCEL if FFMPEG_HWACCEL else "off",
                    frames_to_capture,
                    burst_span_ms,
                    output_filter_args[1] if output_filter_args else "off",
                    "yes" if pre_input_args else "no",
                    analyze_duration,
                    probe_size,
                )
                continue
            except subprocess.CalledProcessError as e:
                stderr_text = (e.stderr or b"").decode("utf-8", "ignore")
                if is_hdhomerun_stream and os.listdir(tmpdirname):
                    logging.warning(
                        "ffmpeg returned %s for HDHomeRun stream %s but produced frames; validating frames: %s",
                        e.returncode,
                        clean_url,
                        stderr_text[:200],
                    )
                elif "-hwaccel" in command and _ffmpeg_error_suggests_hwaccel_failure(
                    stderr_text
                ):
                    retry_command = _ffmpeg_command_without_hwaccel(command)
                    try:
                        # A failed decoder may leave both complete and partial
                        # frames. Never mix them into the replacement burst or
                        # let an existing output trigger an overwrite prompt.
                        for entry in os.listdir(tmpdirname):
                            os.remove(os.path.join(tmpdirname, entry))
                        retry_timeout = attempt_deadline - time.monotonic()
                        if retry_timeout <= 0:
                            logging.warning(
                                "ffmpeg attempt budget exhausted for %s; skipping software retry",
                                clean_url,
                            )
                            continue
                        logging.warning(
                            "ffmpeg hwaccel failed for %s; retrying software decode: %s",
                            clean_url,
                            stderr_text[:200],
                        )
                        subprocess.run(
                            retry_command,
                            check=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=retry_timeout,
                        )
                    except subprocess.TimeoutExpired:
                        logging.error(
                            "ffmpeg software retry timed out for %s after %ss",
                            clean_url,
                            retry_timeout,
                        )
                        continue
                    except subprocess.CalledProcessError as retry_error:
                        logging.error(
                            "ffmpeg software retry failed for %s: %s",
                            clean_url,
                            (retry_error.stderr or b"").decode("utf-8", "ignore")[:200],
                        )
                        continue
                    except Exception as retry_exc:
                        logging.error(
                            "Error running ffmpeg software retry for %s: %s",
                            clean_url,
                            retry_exc,
                        )
                        continue
                else:
                    logging.error(
                        "ffmpeg failed for %s: %s",
                        clean_url,
                        stderr_text[:200],
                    )
                    continue
            except Exception as e:
                logging.error(
                    "Error running ffmpeg for %s: %s",
                    clean_url,
                    e,
                )
                continue

            try:
                best_frame_path, reject_reason = _select_best_stream_frame(
                    tmpdirname, name
                )
                if best_frame_path:
                    if reject_reason is not None:
                        logging.warning(
                            "[%s] Rejecting stream frame due to %s pattern: %s",
                            name,
                            reject_reason,
                            clean_url,
                        )
                        rejected_capture_reason = reject_reason
                        # Another RTSP transport may deliver a clean burst.
                        continue
                    if _is_valid_png(best_frame_path):
                        _publish_stream_frame(
                            best_frame_path,
                            output_path,
                            name,
                            invert=invert,
                            stabilize_mode=stabilize_mode,
                        )
                        logging.debug(
                            f"Successfully captured frame from stream {clean_url}"
                        )
                        if transport:
                            _set_rtsp_transport(url, transport)
                        return True
                else:
                    logging.error(f"No frames captured from stream {clean_url}")
            except Exception as e:
                logging.error(f"Error capturing frames from stream: {e}")

    if rejected_capture_reason is not None:
        record_preflight_backoff(
            url,
            f"{rejected_capture_reason}_capture",
            PREFLIGHT_BACKOFF_BROWSER_FAIL,
        )
    logging.error(f"Error capturing frame with {FFMPEG_PATH}: {clean_url}")
    return False


def apply_dark_mode(img, rng=30, txt_rng=120):
    arr = np.asarray(
        img.convert("RGB")
    ).copy()  # copy to avoid "assignment destination is read-only" errors
    dark = arr <= rng
    light = arr >= 255 - txt_rng
    mask = dark.any(axis=-1) | light.any(axis=-1)
    arr[mask] = 255 - arr[mask]
    return Image.fromarray(arr)


def capture_screenshot_and_har_light(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    proxy=None,
    dark=True,
    stealth=False,
    stabilize_mode="off",
):
    """
    Capture a screenshot of a URL using wkhtmltoimage (WebKit).
    """
    proxy = validate_proxy(proxy)
    url = validate_url(url)
    clean_url = sanitize_url(url)
    if url is None:
        logging.warning("Invalid URL provided for screenshot capture")
        return False
    # Check if wkhtmltoimage is available
    if shutil.which("wkhtmltoimage") is None:
        logging.warning("wkhtmltoimage is not installed or not in the system path.")
        return False

    timeout = max(timeout, 10)

    # We'll stage a temporary filename for the "in-progress" PNG
    tmp_path = output_path.replace(".png", ".tmp.png")
    lsuccess = False
    start_time = time.time()

    lua = UA
    if stealth:
        chrome_path = get_chrome_path()
        cv = get_chrome_version(chrome_path)
        lua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36"
            % cv
        )

    command = [
        "wkhtmltoimage",
        "--width",
        "1920",
        "--height",
        "1080",
        "--javascript-delay",
        str(5000),
        "--quiet",
        "--zoom",
        "1",
        "--quality",
        "100",
        "--enable-javascript",
        "--custom-header",
        "User-Agent",
        lua,
        "--custom-header-propagation",
        url,
        tmp_path,
    ]

    try:
        # Run wkhtmltoimage
        result = subprocess.run(
            command,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )

        if result.returncode != 0:
            # logging.warning(f"wkhtmltoimage failed (returncode {result.returncode}): {result.stderr.decode('utf-8','ignore')}")
            logging.warning(f"wkhtmltoimage failed (returncode {result.returncode}): ")
            return False

        # Process the output file
        if not os.path.exists(tmp_path):
            return False

        # Open and convert the image
        with Image.open(tmp_path) as image:
            image = image.convert("RGB")  # ensure RGB
            try:
                reject_reason = _captured_frame_rejection_reason(image)
            except Exception as exc:
                logging.warning(
                    "[%s] Light screenshot rejection checks failed; keeping capture: %s",
                    name,
                    exc,
                )
                reject_reason = None
            if reject_reason is not None:
                logging.warning(
                    "[%s] Captured image rejected due to %s frame: %s",
                    name,
                    reject_reason,
                    clean_url,
                )
                record_preflight_backoff(
                    url,
                    (
                        "lightweight_blank"
                        if reject_reason == "blank"
                        else f"{reject_reason}_capture"
                    ),
                    PREFLIGHT_BACKOFF_BROWSER_FAIL,
                )
                os.unlink(tmp_path)
                return False

            try:
                image = _postprocess_still_image(
                    image,
                    output_path,
                    name,
                    dark=dark,
                    stabilize_mode=stabilize_mode,
                )
            except Exception as exc:
                logging.warning(
                    "[%s] Light screenshot postprocess failed; keeping raw capture: %s",
                    name,
                    exc,
                )
            image.save(tmp_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)

        # Rename from .tmp.png to final .png
        # Validate the temporary file before renaming so we don't
        # replace the output with an incomplete image.
        if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
            add_timestamp(tmp_path, name, invert=invert)
            # /tmp can be on a different filesystem than SCREENSHOT_DIRECTORY.
            # Use a cross-device safe move to avoid EXDEV ("Invalid cross-device link").
            try:
                os.replace(tmp_path, output_path)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.move(tmp_path, output_path)
            lsuccess = True

        # If you capture HAR data, do that here as well...
        logging.debug(
            f"Successfully captured light screenshot for {clean_url} at {output_path} "
            f"({round(time.time() - start_time, 3)}s)"
        )
        return lsuccess

    except subprocess.TimeoutExpired:
        logging.warning("wkhtmltoimage timed out for %s after %ss", clean_url, timeout)
        return False
    except Exception as e:
        logging.error(f"Error in capture_screenshot_and_har_light: {e}")
        return False

    finally:
        # Cleanup partial file if unsuccessful
        if not lsuccess and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _hwaccel_enabled() -> bool:
    return bool(FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false")


def kill_driver_process(driver):
    """Clean up a still-running owned driver without delaying a completed quit."""
    pid = None
    try:
        process = getattr(getattr(driver, "service", None), "process", None)
        # Selenium's quit already waits for its service to stop. Reap/check the
        # owned Popen first: a dead driver's numeric PID may since be reused.
        if process is None or process.poll() is not None:
            return
        if process.pid:
            pid = process.pid
            chrome_process = psutil.Process(pid)
            # Signal the entire owned tree before waiting. Waiting per child
            # both multiplies the cleanup budget and abandons siblings when a
            # single child ignores SIGTERM. Keep Process objects for PID reuse
            # protection during subsequent signals.
            try:
                children = chrome_process.children(recursive=True)
            except psutil.NoSuchProcess:
                children = []
            targets = [*children, chrome_process]
            for target in targets:
                try:
                    target.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            _, alive = psutil.wait_procs(targets, timeout=3)
            for target in alive:
                try:
                    target.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if alive:
                _, survivors = psutil.wait_procs(alive, timeout=2)
                if survivors:
                    logging.warning(
                        "Browser cleanup left %d processes after kill", len(survivors)
                    )
    except psutil.NoSuchProcess:
        logging.debug(f"Process {pid} already exited before termination attempt.")
    except Exception as e:
        logging.error(f"Error killing Chrome process: {e}")
    finally:
        # Ensure future calls create a new driver
        if hasattr(_driver_local, "driver"):
            _driver_local.driver = None


def launch_headless_chrome(driver_options, version=None):
    driver = None
    try:
        # note - version not working
        # service = Service(ChromeDriverManager(version=str(version)).install())
        # service = Service(ChromeDriverManager().install())
        # driver = webdriver.Chrome(service=service, options=driver_options)
        driver = get_driver(driver_options)
        # driver = webdriver.Chrome(service=service, options=driver_options, version_main=version)
        # driver = uc.Chrome(options=driver_options, version_main=version)
    except Exception as e:
        logging.error("BAD DRIVER ERROR %s", e)
        # _purge_driver_cache() # maybe?
    return driver


def apply_stealth_options(driver_options):
    """Randomize options to better mimic a human browser."""
    width = random.randint(1200, 1920)
    height = random.randint(800, 1080)
    driver_options.add_argument(f"--window-size={width},{height}")
    driver_options.add_argument(f"--user-agent={random_user_agent()}")
    driver_options.add_argument("--disable-blink-features=AutomationControlled")
    driver_options.add_argument("--disable-infobars")
    driver_options.add_argument("--disable-extensions")


def _is_hubitat_cloud_dashboard_url(url: str | None) -> bool:
    lower_url = str(url or "").strip().lower()
    parsed = urlparse(lower_url)
    is_cloud_dashboard = (
        parsed.hostname == "cloud.hubitat.com"
        and "/apps/" in parsed.path
        and ("/ui" in parsed.path or "/dashboard/" in parsed.path)
    )
    is_local_dashboard = (
        "/apps/api/" in lower_url
        and "/dashboard/" in lower_url
        and "access_token=" in lower_url
    )
    # Hubitat Dashboard v2 also has a local UI route without a query token.
    is_local_ui = (
        parsed.hostname in capture_policy.CAPTURE_POLICY.get("hubitat_hosts", [])
        and re.fullmatch(r"/dashboard/ui/\d+/?", parsed.path) is not None
    )
    return is_cloud_dashboard or is_local_dashboard or is_local_ui


def _browser_capture_profile(
    url: str | None, name: str | None = None
) -> dict[str, object]:
    """Return capture tuning hints for dynamic sites that need extra handling."""

    lower_url = str(url or "").strip().lower()
    lower_name = str(name or "").strip().lower()
    combined = f"{lower_name} {lower_url}"
    parsed_url = urlparse(lower_url)
    host = parsed_url.hostname or ""

    is_earthcam = url_matches_host(lower_url, "earthcam.com")
    is_electricity_map = url_matches_host(lower_url, "electricitymaps.com")
    is_flightradar = url_matches_host(lower_url, "flightradar24.com")
    is_flightaware = url_matches_host(lower_url, "flightaware.com")
    is_faa = url_matches_host(lower_url, "faa.gov") or lower_name == "faa"
    is_gpsjam = url_matches_host(lower_url, "gpsjam.org")
    is_kubra_stormcenter = (
        url_matches_host(lower_url, "kubra.io") or lower_name == "comed"
    )
    is_comed_price = (
        lower_name == "comedprice"
        or url_matches_host(lower_url, "hourlypricing.comed.com")
        or "comed_price_wall" in lower_url
    )
    is_lightning_map = url_matches_host(lower_url, "blitzortung.org")
    is_skyline_webcams = url_matches_host(lower_url, "skylinewebcams.com")
    is_storefront = url_matches_host(lower_url, "abt.com") or lower_name in {
        "abt",
        "abt.com",
    }
    is_windy_map = url_matches_host(lower_url, "windy.com")
    is_youtube = url_matches_host(lower_url, "youtube.com") or url_matches_host(
        lower_url, "youtu.be"
    )
    is_tv_guide = (
        lower_name == "tvguide"
        or url_matches_host(lower_url, "tvguide.com")
        or "tv_guide_wall" in lower_url
    )
    is_adblock_wall = "adblock_wall" in lower_url
    is_youtube_streams = is_youtube and (
        "/streams" in parsed_url.path or "streams" in lower_name
    )
    is_news_site = lower_name in {
        "abc7",
        "apnews",
        "bbc",
        "espn",
        "foxnews",
        "msn",
        "reutersscience",
        "scmp",
        "slashdot",
        "yahoo",
    } or any(
        token in host
        for token in (
            "abc7chicago.com",
            "apnews.com",
            "bbc.com",
            "espn.com",
            "foxnews.com",
            "msn.com",
            "reuters.com",
            "slashdot.org",
            "scmp.com",
            "yahoo.com",
        )
    )
    is_network_speed_test = url_matches_host(lower_url, "fast.com") or lower_name in {
        "fast",
        "fast.com",
    }
    is_local_admin_page = (
        lower_name == "modem"
        or "modem" in combined
        or host in capture_policy.CAPTURE_POLICY.get("admin_hosts", [])
        or (
            bool(host)
            and _is_lan_target(host)
            and host not in {"127.0.0.1", "localhost"}
            and host
            not in capture_policy.CAPTURE_POLICY.get("admin_excluded_hosts", [])
            and any(token in combined for token in ("router", "gateway", "admin"))
        )
    )
    is_browser_diagnostics_page = lower_name in {
        "adblock",
        "antibot",
        "browserleaks",
        "creepjs",
        "darkmode",
        "headers",
    } or host in {
        "abrahamjuliot.github.io",
        "bot.sannysoft.com",
        "browserleaks.com",
        "d3ward.github.io",
        "webbrowsertools.com",
        "www.xhaus.com",
    }
    is_public_data_dashboard = lower_name in {
        "apocalypseews",
        "aps",
        "aqi",
        "argonnesrstatus",
        "chicagorespiratoryillness",
        "ecmwf",
        "fermilabftbfstatus",
        "fires",
        "gasprice",
        "icecover",
        "mccookhydrograph",
        "moongravity",
        "piracy",
        "saltcreekwooddale",
        "stream",
        "swpcsolarwind",
        "tarpreservoirlevels",
        "wastewater",
    } or host in {
        "apps.usgs.gov",
        "aqicn.org",
        "charts.ecmwf.int",
        "ews.kylemcdonald.net",
        "firms.modaps.eosdis.nasa.gov",
        "ftbf.fnal.gov",
        "gasprices.aaa.com",
        "gis.cdc.gov",
        "iwss.uillinois.edu",
        "mwrd.org",
        "seismologie.be",
        "water.noaa.gov",
        "waterwatch.usgs.gov",
        "www.chicago.gov",
        "www.glerl.noaa.gov",
        "www.icc-ccs.org",
        "www.swpc.noaa.gov",
        "www3.aps.anl.gov",
    }
    is_listing_or_shop_page = lower_name in {
        "att",
        "costco",
        "redfin",
        "verizon",
        "walgreens",
    } or host in {
        "att.com",
        "costco.com",
        "redfin.com",
        "verizon.com",
        "walgreens.com",
        "www.redfin.com",
    }
    is_status_page = lower_name in {"deeplisten"} or host in {
        "deeplisten.tv",
        "www.deeplisten.tv",
    }
    is_boatnerd_ais = url_matches_host(lower_url, "ais.boatnerd.com") or (
        "boatnerd" in combined and "ais" in combined
    )
    is_zoom_earth = "zoom.earth" in lower_url or lower_name == "zoomearth"
    is_arcgis_dashboard = any(
        token in lower_url
        for token in (
            "arcgis.com",
            "arcgisusercontent.com",
            "arcg.is",
            "experience.arcgis.com",
            "storymaps.arcgis.com",
        )
    ) or (
        ("arcgis" in combined or "esri" in combined)
        and any(
            token in combined
            for token in (
                "dashboard",
                "fire",
                "flood",
                "gis",
                "map",
                "outage",
                "perimeter",
                "smoke",
                "storm",
                "weather",
                "wildfire",
            )
        )
    )
    is_public_map_dashboard = is_arcgis_dashboard or any(
        token in lower_url
        for token in (
            "bing.com/maps",
            "earthquake.usgs.gov/earthquakes/map",
            "embed.waze.com",
            "google.com/maps",
            "zoom.earth",
        )
    )
    is_hubitat_cloud_dashboard = _is_hubitat_cloud_dashboard_url(lower_url)
    is_flight_tracker = (
        lower_name in {"faa", "flight radar", "flightradar", "flightradar24"}
        or is_flightradar
        or is_flightaware
        or url_matches_host(lower_url, "faa.gov")
        or "flight tracker" in combined
        or "flight-tracker" in combined
        or "live flight" in combined
        or (
            "faa" in combined
            and any(
                token in combined
                for token in ("track", "traffic", "radar", "airport", "flight")
            )
        )
    )
    if is_hubitat_cloud_dashboard:
        return {
            "allow_private_network_images": True,
            "auto_dedicated_xpath": "",
            "continue_after_load_timeout": False,
            "hide_selectors": (),
            "hubitat_cloud_dashboard": True,
            "page_load_strategy": "",
            "popup_xpaths": (),
            "post_load_delay": 3.0,
            "prefer_rich_graphics": False,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
        }

    if (
        not is_flight_tracker
        and not is_earthcam
        and not is_electricity_map
        and not is_gpsjam
        and not is_kubra_stormcenter
        and not is_comed_price
        and not is_lightning_map
        and not is_skyline_webcams
        and not is_storefront
        and not is_windy_map
        and not is_youtube
        and not is_tv_guide
        and not is_news_site
        and not is_network_speed_test
        and not is_local_admin_page
        and not is_browser_diagnostics_page
        and not is_public_data_dashboard
        and not is_listing_or_shop_page
        and not is_status_page
        and not is_boatnerd_ais
        and not is_public_map_dashboard
    ):
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "",
            "click_xpaths": (),
            "continue_after_load_timeout": False,
            "hide_selectors": (),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "",
            "popup_xpaths": (),
            "post_load_delay": 0.0,
            "prefer_rich_graphics": False,
            "timeout_floor": 30,
            "viewport": None,
            "force_dark_visual_filter": False,
        }

    if is_tv_guide:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//*[@id='tv-guide-wall']",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (),
            "post_load_delay": 2.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 35,
            "viewport": (1600, 900),
            "force_dark_visual_filter": False,
        }

    if is_comed_price:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//*[@id='comed-price-wall']",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (),
            "post_load_delay": 2.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 35,
            "viewport": (1600, 900),
            "force_dark_visual_filter": False,
        }

    if is_adblock_wall:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//*[@id='adblock-wall']",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (),
            "post_load_delay": 5.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 35,
            "viewport": (1600, 900),
            "force_dark_visual_filter": False,
        }

    if is_youtube:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": (
                "//*[@id='contents' and ancestor::ytd-rich-grid-renderer] "
                "| //ytd-rich-grid-renderer | //*[@id='contents']"
                if is_youtube_streams
                else "//*[@id='movie_player'] | //*[@id='player']"
            ),
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "ytd-masthead",
                "#masthead-container",
                "#guide",
                "#guide-content",
                "#secondary",
                "#comments",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 7.0 if is_youtube_streams else 5.0,
            "prefer_rich_graphics": True,
            "preserve_visual_media_on_dark_filter": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_news_site:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//*[@id='main-content'] | //main | //article | //body",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                "[id*='newsletter' i]",
                "[class*='newsletter' i]",
                "[id*='subscribe' i]",
                "[class*='subscribe' i]",
                "[id*='paywall' i]",
                "[class*='paywall' i]",
                "[id*='sign-in' i]",
                "[class*='sign-in' i]",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'subscribe')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'subscribe')]",
            ),
            "post_load_delay": 5.0,
            "prefer_rich_graphics": True,
            "preserve_visual_media_on_dark_filter": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_status_page:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//main | //body",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 4.0,
            "prefer_rich_graphics": True,
            "dark_visual_filter_mode": "theme",
            "preserve_visual_media_on_dark_filter": False,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_browser_diagnostics_page:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//main | //body",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                "[id*='ad' i]",
                "[class*='ad' i]",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 4.0,
            "prefer_rich_graphics": True,
            "dark_visual_filter_mode": "theme",
            "preserve_visual_media_on_dark_filter": False,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_public_data_dashboard:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//main | //article | //body",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                "[id*='welcome' i]",
                "[class*='welcome' i]",
                ".modal",
                ".popup",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 6.0,
            "prefer_rich_graphics": True,
            "preserve_visual_media_on_dark_filter": False,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_listing_or_shop_page:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//main | //body",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                "[id*='newsletter' i]",
                "[class*='newsletter' i]",
                "[id*='subscribe' i]",
                "[class*='subscribe' i]",
                "[id*='signup' i]",
                "[class*='signup' i]",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
            ),
            "post_load_delay": 5.0,
            "prefer_rich_graphics": True,
            "dark_visual_filter_mode": "theme",
            "preserve_visual_media_on_dark_filter": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_network_speed_test or is_local_admin_page:
        return {
            "allow_private_network_images": bool(is_local_admin_page),
            "auto_dedicated_xpath": (
                "//body"
                if is_network_speed_test
                else "//*[@id='contents'] | //main | //body"
            ),
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 10.0 if is_network_speed_test else 3.0,
            "prefer_rich_graphics": True,
            "dark_visual_filter_mode": "theme",
            "preserve_visual_media_on_dark_filter": False,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_boatnerd_ais:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "",
            "click_xpaths": ("//button[normalize-space()='Skip']",),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[contains(normalize-space(.),'Welcome to BoatNerd')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_click_delay": 4.0,
            "post_load_delay": 5.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_public_map_dashboard:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": (
                "//body"
                if is_zoom_earth
                else (
                    "//*[contains(@class,'esri-view-root')] | //main | //body"
                    if is_arcgis_dashboard
                    else "//canvas | //*[@id='map'] | //main | //body"
                )
            ),
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                "[id*='welcome' i]",
                "[class*='welcome' i]",
                ".modal",
                ".popup",
                ".leaflet-control-container",
                ".leaflet-control-zoom",
                ".leaflet-control-attribution",
                ".leaflet-popup",
                ".mapboxgl-popup",
                ".maplibregl-popup",
                ".mapboxgl-ctrl-top-left",
                ".mapboxgl-ctrl-top-right",
                ".mapboxgl-ctrl-bottom-left",
                ".mapboxgl-ctrl-bottom-right",
                ".mapboxgl-ctrl-attrib",
                ".maplibregl-ctrl-top-left",
                ".maplibregl-ctrl-top-right",
                ".maplibregl-ctrl-bottom-left",
                ".maplibregl-ctrl-bottom-right",
                ".maplibregl-ctrl-attrib",
                ".esri-ui-top-left",
                ".esri-ui-top-right",
                ".esri-ui-bottom-left",
                ".esri-ui-bottom-right",
                ".esri-attribution",
                ".esri-popup",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
                "//*[contains(@class,'modal')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(normalize-space(.),'Welcome to Zoom Earth')]",
            ),
            "post_load_delay": (
                14.0 if is_zoom_earth else 10.0 if is_arcgis_dashboard else 8.0
            ),
            "prefer_rich_graphics": True,
            "timeout_floor": 60 if is_zoom_earth else 50 if is_arcgis_dashboard else 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_skyline_webcams:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//*[@id='skylinewebcams'] | //*[@id='webcam'] | //iframe[contains(@src,'youtube')]",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                ".breadcrumb",
                ".cam-vert",
                ".adsbygoogle",
                "footer",
                ".footer",
                "[class*='share']",
                "[class*='social']",
                "[id*='share']",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
            ),
            "post_load_delay": 8.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
        }

    if is_earthcam:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//*[@id='ecnPlayer'] | //main",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                ".breadcrumb",
                ".adsbygoogle",
                ".selectorArea",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[contains(@class,'selectorArea')]",
                "//*[@role='dialog']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 4.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 40,
            "viewport": (1920, 1080),
        }

    if is_electricity_map:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//canvas[contains(@class,'maplibregl-canvas')] | //main",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                "aside",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                ".mapboxgl-popup",
                ".maplibregl-popup",
                ".mapboxgl-ctrl-top-left",
                ".mapboxgl-ctrl-top-right",
                ".mapboxgl-ctrl-bottom-left",
                ".mapboxgl-ctrl-bottom-right",
                ".maplibregl-ctrl-top-left",
                ".maplibregl-ctrl-top-right",
                ".maplibregl-ctrl-bottom-left",
                ".maplibregl-ctrl-bottom-right",
                ".mapboxgl-ctrl-attrib",
                ".maplibregl-ctrl-attrib",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 8.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 45,
            "viewport": (1920, 1200),
            "force_dark_visual_filter": True,
        }

    if is_kubra_stormcenter:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//main | //body",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                ".modal",
                ".popup",
                ".esri-ui-top-left",
                ".esri-ui-top-right",
                ".esri-ui-bottom-left",
                ".esri-ui-bottom-right",
                ".esri-attribution",
                ".esri-popup",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
                "//*[contains(@class,'modal')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 8.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
            "force_dark_visual_filter": True,
        }

    if is_gpsjam:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 10.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
        }

    if is_windy_map:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//canvas | //main",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
                ".modal",
                ".popup",
                ".leaflet-control-container",
                ".leaflet-top",
                ".leaflet-bottom",
                ".leaflet-popup",
                ".leaflet-control-zoom",
                ".leaflet-control-attribution",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
                "//*[contains(@class,'modal')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 18.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 60,
            "viewport": (1920, 1080),
        }

    if is_lightning_map:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "//canvas | //main",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "header",
                "nav",
                ".header",
                ".navbar",
                "[role='dialog']",
                "[aria-modal='true']",
                "[id*='cookie']",
                "[class*='cookie']",
                "[id*='consent']",
                "[class*='consent']",
                "iframe[title*='consent']",
                "iframe[src*='consent']",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[contains(@class,'cookie')]",
                "//*[contains(@class,'consent')]",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
            ),
            "post_load_delay": 15.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 60,
            "viewport": (1920, 1080),
        }

    if is_storefront:
        return {
            "allow_private_network_images": False,
            "auto_dedicated_xpath": "",
            "click_xpaths": (),
            "continue_after_load_timeout": True,
            "hide_selectors": (
                "[role='dialog']",
                "[aria-modal='true']",
                "[data-testid*='modal' i]",
                "[data-testid*='popup' i]",
                "[data-testid*='popover' i]",
                "[data-testid*='email' i]",
                "[id*='cookie' i]",
                "[class*='cookie' i]",
                "[id*='consent' i]",
                "[class*='consent' i]",
                "[id*='newsletter' i]",
                "[class*='newsletter' i]",
                "[id*='subscribe' i]",
                "[class*='subscribe' i]",
                "[id*='login' i]",
                "[class*='login' i]",
                "[id*='sign-in' i]",
                "[class*='sign-in' i]",
                "[id*='signin' i]",
                "[class*='signin' i]",
                "[id*='account' i]",
                "[class*='account' i]",
                "[id*='flyout' i]",
                "[class*='flyout' i]",
                "[id*='dropdown' i]",
                "[class*='dropdown' i]",
                "[id*='tooltip' i]",
                "[class*='tooltip' i]",
                "[id*='email-capture' i]",
                "[class*='email-capture' i]",
                "[id*='email-signup' i]",
                "[class*='email-signup' i]",
                "[id*='attentive' i]",
                "[class*='attentive' i]",
                "[id*='privy' i]",
                "[class*='privy' i]",
                "[id*='klaviyo' i]",
                "[class*='klaviyo' i]",
                "[id*='justuno' i]",
                "[class*='justuno' i]",
                "[id*='wisepops' i]",
                "[class*='wisepops' i]",
                "[id*='ltkpopup' i]",
                "[class*='ltkpopup' i]",
                "#onetrust-consent-sdk",
                ".ot-sdk-container",
                ".ot-floating-button",
                "iframe[title*='consent' i]",
                "iframe[src*='consent' i]",
            ),
            "hubitat_cloud_dashboard": False,
            "page_load_strategy": "eager",
            "popup_xpaths": (
                "//*[@role='dialog']",
                "//*[@aria-modal='true']",
                "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'consent')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'subscribe')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'subscribe')]",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'log in for the best experience')]",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'track your orders')]",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save items for later')]",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'view your order history')]",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create an account')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sign-in')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sign-in')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'signin')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'signin')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'account')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'account')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'flyout')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'flyout')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'dropdown')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'dropdown')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email-capture')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email-capture')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email-signup')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email-signup')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'attentive')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'attentive')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'privy')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'privy')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'klaviyo')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'klaviyo')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'justuno')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'justuno')]",
                "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'wisepops')]",
                "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'wisepops')]",
            ),
            "post_load_delay": 5.0,
            "prefer_rich_graphics": True,
            "timeout_floor": 45,
            "viewport": (1920, 1080),
        }

    # Flight-tracking maps are usually large SPA canvases with persistent
    # search/header chrome. They need more settle time and a less stripped-down
    # renderer than a generic webpage capture.
    profile = {
        "allow_private_network_images": False,
        "auto_dedicated_xpath": "//main",
        "click_xpaths": (),
        "continue_after_load_timeout": True,
        "hide_selectors": (
            "#modals",
            "#search-input-wrapper",
            "[data-testid='search']",
            "[data-testid='header__mobile']",
            "[data-testid='header__right-elements']",
            "[data-testid='map__gradient-bg']",
            "[data-testid='sidemenu-content']",
            "[data-testid='most-tracked-flights-widget']",
            "[data-testid='airport-disruptions-widget']",
            "[data-testid='bookmarks-widget']",
            "[data-testid='sidebar__container']",
            ".pointer-events-none.absolute.bottom-0.right-0",
            "aside[class*='w-sidebar']",
            "#pb-slot-fr24-map",
            "[role='dialog']",
            "[aria-modal='true']",
            "[id*='cookie']",
            "[class*='cookie']",
            "[id*='consent']",
            "[class*='consent']",
            "[id*='gdpr']",
            "[class*='gdpr']",
            "iframe[title*='consent']",
            "iframe[src*='consent']",
        ),
        "hubitat_cloud_dashboard": False,
        "page_load_strategy": "eager",
        "popup_xpaths": (
            "//*[@id='modals']//*[self::div or self::section or self::aside or self::dialog]",
            "//*[@role='dialog']",
            "//iframe[contains(@title,'consent') or contains(@src,'consent')]",
        ),
        "post_load_delay": 6.0,
        "prefer_rich_graphics": True,
        "timeout_floor": 45,
        "viewport": (2560, 1440),
    }
    if is_flightradar:
        profile["auto_dedicated_xpath"] = "//*[@id='app']//main | //main"
    elif is_flightaware:
        profile["auto_dedicated_xpath"] = "//*[@id='map'] | //main"
        profile["hide_selectors"] = tuple(profile["hide_selectors"]) + (
            "#mobileNavBar",
            "#topWrapper",
            "#mainBody > header",
            ".dialogOverlay",
            "#onetrust-consent-sdk",
            ".ot-sdk-container",
            ".ot-floating-button",
        )
        profile["popup_xpaths"] = tuple(profile["popup_xpaths"]) + (
            "//*[@id='onetrust-consent-sdk']",
            "//*[contains(@class,'dialogOverlay')]",
        )
    elif is_faa:
        profile["auto_dedicated_xpath"] = "//*[@id='map'] | //main"
    return profile


def _browser_profile_chrome_args(
    profile: dict[str, object], chrome_path: str | None
) -> tuple[str, ...]:
    """Return extra Chrome flags implied by a browser capture profile."""

    args: list[str] = []
    viewport = profile.get("viewport")
    if isinstance(viewport, tuple) and len(viewport) == 2:
        width, height = viewport
        if isinstance(width, int) and isinstance(height, int):
            args.append(f"--window-size={width},{height}")

    if profile.get("prefer_rich_graphics"):
        args.extend(
            (
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--enable-gpu-rasterization",
                "--enable-zero-copy",
                "--use-angle=swiftshader",
            )
        )
        if chrome_path and browser_supports_gl(chrome_path):
            args.append("--use-gl=egl")
    elif (
        chrome_path
        and _hwaccel_enabled()
        and config._machine_supports_hwaccel()
        and browser_supports_gl(chrome_path)
    ):
        args.append("--use-gl=egl")
    else:
        args.append("--disable-gpu")

    if profile.get("force_dark_visual_filter"):
        args.extend(("--force-dark-mode", "--enable-features=WebContentsForceDark"))

    if profile.get("allow_private_network_images"):
        args.extend(
            (
                "--allow-running-insecure-content",
                "--disable-site-isolation-trials",
                "--disable-web-security",
                "--ignore-certificate-errors",
            )
        )
    return tuple(args)


def _apply_browser_site_dom_cleanup(
    driver, selectors: tuple[str, ...] | list[str], name: str
) -> int:
    """Hide known site chrome before capture for dynamic full-screen apps.

    Selector cleanup is deliberately scene-safe. Operator and profile selectors
    can be broad, so do not hide large map/video/camera elements unless the
    target has a strong overlay identity.
    """

    if not selectors:
        return 0
    try:
        removed = driver.execute_script(
            """
            const selectors = arguments[0] || [];
            const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0, 1);
            const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0, 1);
            const varea = Math.max(1, vw * vh);
            const overlayTokens = [
              'modal', 'popup', 'popover', 'dialog', 'overlay', 'drawer',
              'cookie', 'consent', 'gdpr', 'privacy', 'newsletter',
              'subscribe', 'email-signup', 'email-capture', 'signup',
              'headlessui', 'onetrust', 'attentive', 'ltkpopup', 'privy',
              'klaviyo', 'justuno', 'wisepops', 'flyout', 'dropdown',
              'tooltip', 'login', 'sign-in', 'signin', 'account',
              'best-experience', 'rewards'
            ];
            const sceneTokens = [
              'map', 'canvas', 'video', 'player', 'camera', 'webcam',
              'main-content', 'product-grid', 'hero', 'chart', 'graph'
            ];
            function identityFor(el, selector) {
              return [
                selector || '',
                el.id || '',
                typeof el.className === 'string' ? el.className : '',
                el.getAttribute('role') || '',
                el.getAttribute('aria-modal') || '',
                el.getAttribute('data-testid') || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('title') || ''
              ].join(' ').toLowerCase();
            }
            function shouldHideCandidate(el, selector) {
              const tag = String(el.tagName || '').toLowerCase();
              const style = window.getComputedStyle(el);
              if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
              const rect = el.getBoundingClientRect();
              if (!rect || rect.width <= 0 || rect.height <= 0) return false;
              if (rect.bottom < 0 || rect.top > vh || rect.right < 0 || rect.left > vw) return false;
              const frac = (rect.width * rect.height) / varea;
              const identity = identityFor(el, selector);
              const hasOverlayHint = overlayTokens.some((token) => identity.includes(token));
              const hasSceneHint = sceneTokens.some((token) => identity.includes(token));
              const isModal = el.getAttribute('aria-modal') === 'true' || el.getAttribute('role') === 'dialog';
              const isSceneTag = ['body', 'html', 'main', 'canvas', 'video', 'img'].includes(tag);

              if (!hasOverlayHint && !isModal) {
                if (isSceneTag && frac > 0.05) return false;
                if (hasSceneHint && frac > 0.12) return false;
                if (frac > 0.78) return false;
              }
              return true;
            }
            let removed = 0;
            for (const selector of selectors) {
              if (!selector) continue;
              for (const el of document.querySelectorAll(selector)) {
                try {
                  if (!shouldHideCandidate(el, selector)) continue;
                  el.style.setProperty('display', 'none', 'important');
                  el.style.setProperty('visibility', 'hidden', 'important');
                  el.style.setProperty('opacity', '0', 'important');
                  removed++;
                } catch (e) {
                  // ignore per-node failures
                }
              }
            }
            return removed;
            """,
            list(selectors),
        )
        return int(removed or 0)
    except Exception as exc:
        logging.debug("[%s] site DOM cleanup failed: %s", name, exc)
        return 0


def _apply_map_dark_background(driver, url: str, name: str) -> bool:
    """Tone down two known raster maps without inverting measurement colors."""

    host = (urlparse(url).hostname or "").lower()
    if host in {"allsky7.net", "www.allsky7.net"}:
        selector = '.gm-style img[src*="maps.googleapis.com/maps/vt"]'
        visual_filter = "invert(1) hue-rotate(180deg) brightness(.75)"
    elif host in {"radmon.org", "www.radmon.org"}:
        # Radmon paints readings into the same canvas as its map. Dimming keeps
        # their hues intact; inversion would change the radiation color scale.
        selector = ".ol-layer canvas"
        visual_filter = "brightness(.55)"
    else:
        return False
    try:
        return bool(
            driver.execute_script(
                """
                const [selector, visualFilter] = arguments;
                let style = document.getElementById('glimpser-dark-map-background');
                if (!style) {
                  style = document.createElement('style');
                  style.id = 'glimpser-dark-map-background';
                  document.head.appendChild(style);
                }
                style.textContent = `
                  html, body, #status, .tab-content, .tab-pane {
                    background-color: #101820 !important;
                    color: #e8eef6 !important;
                    color-scheme: dark;
                  }
                  #status a { color: #7dd3fc !important; }
                  #status input, #status select {
                    background-color: #172536 !important;
                    color: #e8eef6 !important;
                    border-color: #475569 !important;
                  }
                  ${selector} { filter: ${visualFilter} !important; }
                `;
                return document.querySelectorAll(selector).length > 0;
                """,
                selector,
                visual_filter,
            )
        )
    except Exception as exc:
        logging.debug("[%s] map dark background unavailable: %s", name, exc)
        return False


def _apply_browser_dark_preference(driver, dark: bool, invert: bool = False) -> None:
    """Request native dark CSS and emulate unsupported pages before navigation."""

    if not dark or invert:
        return
    # These commands are independent: older Chromium can support the native
    # preference even when automatic page recoloring is unavailable.
    for command, params in (
        (
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-color-scheme", "value": "dark"}]},
        ),
        ("Emulation.setAutoDarkModeOverride", {"enabled": True}),
    ):
        try:
            driver.execute_cdp_cmd(command, params)
        except Exception as exc:
            logging.debug("Browser dark preference %s unavailable: %s", command, exc)


def _apply_force_dark_visual_filter(
    driver,
    name: str,
    preserve_visual_media: bool = False,
    mode: str = "invert",
) -> bool:
    """Apply a scoped visual dark fallback for sites that ignore dark emulation."""

    try:
        return bool(
            driver.execute_script(
                """
                const preserveVisualMedia = Boolean(arguments[0]);
                const mode = String(arguments[1] || 'invert').toLowerCase();
                const styleId = 'glimpser-force-dark-visual-filter';
                const root = document.documentElement;
                root.classList.remove('glimpser-force-dark-visual-filter');
                root.classList.remove('glimpser-force-dark-theme');
                root.classList.add('glimpser-force-dark-visual-filter');
                if (mode === 'theme') {
                  root.classList.add('glimpser-force-dark-theme');
                }
                if (preserveVisualMedia) {
                  root.classList.add('glimpser-preserve-visual-media');
                } else {
                  root.classList.remove('glimpser-preserve-visual-media');
                }

                let meta = document.querySelector('meta[name="color-scheme"]');
                if (!meta) {
                  meta = document.createElement('meta');
                  meta.setAttribute('name', 'color-scheme');
                  document.head.appendChild(meta);
                }
                meta.setAttribute('content', 'dark');

                if (!document.getElementById(styleId)) {
                  const style = document.createElement('style');
                  style.id = styleId;
                  style.textContent = `
                    html.glimpser-force-dark-visual-filter,
                    html.glimpser-force-dark-visual-filter body {
                      background: #f8fafc !important;
                      color: #111827 !important;
                    }
                    html.glimpser-force-dark-visual-filter:not(.glimpser-force-dark-theme) {
                      filter: invert(1) hue-rotate(180deg) brightness(.65) contrast(1.08);
                    }
                    html.glimpser-force-dark-visual-filter iframe {
                      background: #05070a !important;
                    }
                    html.glimpser-force-dark-visual-filter.glimpser-preserve-visual-media img,
                    html.glimpser-force-dark-visual-filter.glimpser-preserve-visual-media picture,
                    html.glimpser-force-dark-visual-filter.glimpser-preserve-visual-media video,
                    html.glimpser-force-dark-visual-filter.glimpser-preserve-visual-media canvas,
                    html.glimpser-force-dark-visual-filter.glimpser-preserve-visual-media iframe,
                    html.glimpser-force-dark-visual-filter.glimpser-preserve-visual-media svg {
                      filter: invert(1) hue-rotate(180deg) brightness(1.35) contrast(.93);
                    }
                    html.glimpser-force-dark-theme,
                    html.glimpser-force-dark-theme body {
                      background: #05070a !important;
                      color: #e7edf4 !important;
                      filter: none !important;
                    }
                    html.glimpser-force-dark-theme body,
                    html.glimpser-force-dark-theme main,
                    html.glimpser-force-dark-theme section,
                    html.glimpser-force-dark-theme article,
                    html.glimpser-force-dark-theme nav,
                    html.glimpser-force-dark-theme div,
                    html.glimpser-force-dark-theme table,
                    html.glimpser-force-dark-theme thead,
                    html.glimpser-force-dark-theme tbody,
                    html.glimpser-force-dark-theme tr,
                    html.glimpser-force-dark-theme td,
                    html.glimpser-force-dark-theme th {
                      background-color: #0b1118 !important;
                      color: #e7edf4 !important;
                      border-color: #334155 !important;
                    }
                    html.glimpser-force-dark-theme a {
                      color: #7dd3fc !important;
                    }
                    html.glimpser-force-dark-theme button,
                    html.glimpser-force-dark-theme input,
                    html.glimpser-force-dark-theme select,
                    html.glimpser-force-dark-theme textarea {
                      background: #111827 !important;
                      color: #f8fafc !important;
                      border-color: #475569 !important;
                    }
                  `;
                  document.head.appendChild(style);
                }
                return true;
                """,
                bool(preserve_visual_media),
                str(mode or "invert"),
            )
        )
    except Exception as exc:
        logging.debug("[%s] force dark visual filter failed: %s", name, exc)
        return False


_HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT = r"""
const cameraHealth = arguments[0] || {};
const dashboardName = arguments[1] || "";
const cameraLabels = arguments[2] || {};
return (function () {
  function applyEyebatHubitatLayout() {
    const viewportWidth = Math.max(320, window.innerWidth || document.documentElement.clientWidth || 1600);
    const gap = 10;
    const v2Items = [...document.querySelectorAll([
      '.vgl-item[data-tour^="DashboardItem_"]',
      '[data-tour^="DashboardItem_"]',
      '[data-testid^="DashboardItem_"]',
      '[id^="DashboardItem_"]',
      '.react-grid-item',
      '.grid-stack-item',
    ].join(','))];
    const legacyItems = v2Items.length ? [] : [...document.querySelectorAll([
      '.tile',
      '.dashboard-tile',
      '[class*="dashboard-tile"]',
      '[class*="DashboardTile"]',
    ].join(','))];
    const allItems = v2Items.length ? v2Items : legacyItems;
    const isLegacyDashboard = !v2Items.length;
    function absoluteUrl(raw) {
      const value = String(raw || '').trim();
      if (!value) return '';
      try {
        return new URL(value, window.location.href).href;
      } catch (e) {
        return value;
      }
    }

    const materialIconLiterals = new Set([
      'add',
      'check_circle',
      'menu',
      'more_horiz',
      'more_vert',
      'settings',
    ]);

    function isMaterialIconLiteral(value) {
      return materialIconLiterals.has(String(value || '').trim());
    }

    function hideMaterialIconTextChrome() {
      const selector = [
        'button',
        '[role="button"]',
        '.material-icons',
        '.material-symbols-outlined',
        '.material-symbols-rounded',
        '.v-icon',
        '.mdi',
        '[class*="icon"]',
        '[class*="Icon"]',
        '[class*="menu"]',
        '[class*="Menu"]',
      ].join(',');
      for (const el of document.querySelectorAll(selector)) {
        if (!isMaterialIconLiteral(el.textContent)) continue;
        el.style.setProperty('display', 'none', 'important');
        el.style.setProperty('visibility', 'hidden', 'important');
        el.style.setProperty('width', '0', 'important');
        el.style.setProperty('height', '0', 'important');
        el.style.setProperty('overflow', 'hidden', 'important');
      }

      const walker = document.createTreeWalker(
        document.body,
        window.NodeFilter ? window.NodeFilter.SHOW_TEXT : 4
      );
      const parents = new Set();
      while (walker.nextNode()) {
        const textNode = walker.currentNode;
        if (isMaterialIconLiteral(textNode.nodeValue)) {
          parents.add(textNode.parentElement);
        }
      }
      for (const parent of parents) {
        if (!parent) continue;
        const inChrome = parent.closest(
          'button, [role="button"], header, nav, .toolbar, .v-toolbar, .v-app-bar, [class*="menu"], [class*="Menu"]'
        );
        if (!inChrome && String(parent.textContent || '').trim().length > 16) {
          continue;
        }
        parent.style.setProperty('display', 'none', 'important');
        parent.style.setProperty('visibility', 'hidden', 'important');
        parent.style.setProperty('width', '0', 'important');
        parent.style.setProperty('height', '0', 'important');
        parent.style.setProperty('overflow', 'hidden', 'important');
      }

      const viewportHeight = Math.max(
        document.documentElement.clientHeight || 0,
        window.innerHeight || 0,
        320
      );
      for (const el of document.querySelectorAll('button, [role="button"]')) {
        const rect = el.getBoundingClientRect();
        if (!rect || rect.width <= 0 || rect.height <= 0) continue;
        const insideDashboardItem = el.closest(
          '.vgl-item[data-tour^="DashboardItem_"], [data-tour^="DashboardItem_"]'
        );
        if (insideDashboardItem) continue;
        const smallFloatingControl = rect.width <= 72 && rect.height <= 72;
        const nearViewportEdge = rect.top <= 80 || rect.bottom >= viewportHeight - 80;
        if (!smallFloatingControl || !nearViewportEdge) continue;
        el.style.setProperty('display', 'none', 'important');
        el.style.setProperty('visibility', 'hidden', 'important');
        el.style.setProperty('width', '0', 'important');
        el.style.setProperty('height', '0', 'important');
        el.style.setProperty('overflow', 'hidden', 'important');
      }
    }
    hideMaterialIconTextChrome();

    function imageSourceForItem(item) {
      const img = item.querySelector(
        [
          "img[src*='last_screenshot']",
          "img[src*='clean_screenshot']",
          "img[src*='embedded_screenshot']",
          "img[src*='/screenshots/']",
          "img[src*='latest_camera']",
        ].join(',')
      );
      if (img) return absoluteUrl(img.currentSrc || img.src);

      for (const el of [item, ...item.querySelectorAll('*')]) {
        const background = window.getComputedStyle(el).backgroundImage || '';
        const match = background.match(/url\((['"]?)(.*?)\1\)/);
        const source = absoluteUrl(match && match[2]);
        if (
          source.includes('last_screenshot') ||
          source.includes('clean_screenshot') ||
          source.includes('embedded_screenshot') ||
          source.includes('/screenshots/') ||
          source.includes('latest_camera')
        ) {
          return source;
        }
      }
      return '';
    }

    function imageLabelForItem(item, src) {
      const lines = String(item.innerText || '').trim().split(/\n+/)
        .map((line) => line.trim())
        .filter((line) => line && !isMaterialIconLiteral(line));
      const text = lines[0] || '';
      const parts = new URL(src, window.location.href).pathname.split('/').filter(Boolean);
      const endpoint = parts.findIndex((part) => ['last_screenshot', 'clean_screenshot', 'embedded_screenshot', 'screenshots'].includes(part));
      const camera = endpoint >= 0 ? parts[endpoint + 1] : '';
      if (camera) {
        let name = camera;
        try { name = decodeURIComponent(camera); } catch { /* Retain malformed source text. */ }
        return Object.prototype.hasOwnProperty.call(cameraLabels, name)
          ? cameraLabels[name] : name.replace(/_/g, ' ');
      }
      if (text && text.length <= 48) return text.replace(/^Eyebat Visual\s*[-:]\s*/i, '');
      return 'Camera';
    }

    // The network wall should give its charts room instead of repeating the
    // television lineup already shown on the separate Media dashboard.
    const selectedItems = allItems.filter((item) => {
      const src = imageSourceForItem(item);
      if (dashboardName === 'HubitatNetwork' && src &&
          ['WBBM-TV', 'WMAQ', 'WGN', 'WFLD', 'ABC7', 'TVGuide'].includes(imageLabelForItem(item, src))) {
        item.style.setProperty('display', 'none', 'important');
        return false;
      }
      return true;
    });
    const imageItems = selectedItems.filter((item) => imageSourceForItem(item));

    if (!imageItems.length && !allItems.length) {
      return {hidden: 0, images: 0, statuses: 0};
    }

    function setBox(item, x, y, width, height) {
      item.style.setProperty('display', 'block', 'important');
      item.style.setProperty('position', 'absolute', 'important');
      item.style.setProperty('left', '0', 'important');
      item.style.setProperty('top', '0', 'important');
      item.style.setProperty('transform', `translate3d(${x}px, ${y}px, 0px)`, 'important');
      item.style.setProperty('width', `${width}px`, 'important');
      item.style.setProperty('height', `${height}px`, 'important');
      item.style.setProperty('box-sizing', 'border-box', 'important');
      item.style.setProperty('margin', '0', 'important');
      item.style.setProperty('max-width', 'none', 'important');
      item.style.setProperty('max-height', 'none', 'important');
      item.style.setProperty('overflow', 'hidden', 'important');
    }

    function fillImageTile(item) {
      const img = item.querySelector(
        "img[src*='last_screenshot'], img[src*='clean_screenshot']"
      );
      if (!img) return;

      const header = item.querySelector('.flex.flex-row.items-center.justify-center');
      if (header) header.remove();

      const tile = item.querySelector('.ui-rounded-md') || item;
      const content = img.closest('.flex-1.max-h-full') || img.parentElement;
      const wrapper = content ? content.parentElement : null;
      const outer = wrapper ? wrapper.parentElement : null;

      for (const el of [tile, outer, wrapper, content]) {
        if (!el) continue;
        el.style.setProperty('box-sizing', 'border-box', 'important');
        el.style.setProperty('height', '100%', 'important');
        el.style.setProperty('width', '100%', 'important');
        el.style.setProperty('margin', '0', 'important');
        el.style.setProperty('max-height', 'none', 'important');
        el.style.setProperty('overflow', 'hidden', 'important');
      }
      tile.style.setProperty('padding', '0', 'important');
      tile.style.setProperty('border-radius', '8px', 'important');
      tile.style.setProperty('background', '#0f172a', 'important');

      img.classList.remove('mt-2');
      img.style.setProperty('display', 'block', 'important');
      img.style.setProperty('height', '100%', 'important');
      img.style.setProperty('width', '100%', 'important');
      img.style.setProperty('margin', '0', 'important');
      img.style.setProperty('max-height', 'none', 'important');
      img.style.setProperty('max-width', 'none', 'important');
      img.style.setProperty('object-fit', 'cover', 'important');
    }

    function normalizeStatusTile(item, large = false) {
      const tile = item.querySelector('.ui-rounded-md') || item;
      tile.style.setProperty(
        'background',
        'linear-gradient(135deg, #101a26, #172536)',
        'important'
      );
      tile.style.setProperty('background-color', '#101a26', 'important');
      tile.style.setProperty('border', '1px solid rgba(148, 163, 184, 0.28)', 'important');
      tile.style.setProperty('border-radius', '8px', 'important');
      tile.style.setProperty('box-shadow', 'inset 4px 0 0 #38bdf8', 'important');
      tile.style.setProperty('color', '#e8eef6', 'important');
      tile.style.setProperty('overflow', 'hidden', 'important');
      tile.style.setProperty('box-sizing', 'border-box', 'important');
      tile.style.setProperty('width', '100%', 'important');
      tile.style.setProperty('height', '100%', 'important');
      tile.style.setProperty('max-width', 'none', 'important');
      tile.style.setProperty('max-height', 'none', 'important');
      if (large) {
        tile.style.setProperty('display', 'flex', 'important');
        tile.style.setProperty('flex-direction', 'column', 'important');
        tile.style.setProperty('align-items', 'center', 'important');
        tile.style.setProperty('justify-content', 'center', 'important');
        tile.style.setProperty('gap', '16px', 'important');
        tile.style.setProperty('padding', '24px', 'important');
        tile.style.setProperty('border-radius', '16px', 'important');
        tile.style.setProperty('box-shadow', 'inset 6px 0 0 #38bdf8, 0 18px 50px rgba(0, 0, 0, 0.22)', 'important');
      }
      for (const node of tile.querySelectorAll('*')) {
        node.style.setProperty('color', '#e8eef6', 'important');
        if (large) {
          node.style.setProperty('font-size', 'clamp(18px, 1.8vw, 28px)', 'important');
          node.style.setProperty('line-height', '1.25', 'important');
        }
      }
      for (const node of tile.querySelectorAll('button, [role="button"], .v-btn, .menu')) {
        node.style.setProperty('display', 'none', 'important');
      }
    }

    function statusLinesForItem(item) {
      // Hidden source tiles lose innerText's layout separators on later passes.
      // Keep separate label/value text nodes instead of joining a device label and its state.
      if (item.__eyebatStatusLines) return item.__eyebatStatusLines;
      const walker = document.createTreeWalker(item, window.NodeFilter.SHOW_TEXT);
      const textParts = [];
      while (walker.nextNode()) {
        const parent = walker.currentNode.parentElement;
        if (parent && parent.closest('script, style, .material-icons')) continue;
        const text = String(walker.currentNode.nodeValue || '').trim();
        // Hubitat embeds reported states inside controls. Other button text
        // remains excluded; never infer state from an action's aria-label.
        const reportedState = parent && parent.closest('.dashboard-text-color') &&
          /^(open|closed|opening|closing|locked|unlocked|wet|dry|unknown)$/i.test(text);
        if (parent && parent.closest('button, [role="button"]') &&
            !/^(on|off)$/i.test(text) && !reportedState) continue;
        if (text) textParts.push(text);
      }
      const cleanedLines = textParts
        .flatMap((text) => text.split(/\n+/))
        .map((line) => line
          .replace(/^\.+/, '')
          .replace(/\b(check_circle|add|settings|more_horiz|more_vert|skip_next|skip_previous|volume_up)\b/g, '')
          .replace(/([0-9%°])([A-Z][a-z]+)/g, '$1 $2')
          .replace(/(\d+)%\s+\1(?=[A-Za-z])/g, '$1% ')
          .replace(/\bhome\s+(Armed|Disarmed)/gi, '$1')
          .replace(/\s+/g, ' ')
          .trim())
        .filter((line) => line && line !== '...');
      // Dashboard v1 can hide icon text while retaining the reported state
      // as a class on .tile-primary. Read only explicit, unambiguous states.
      if (cleanedLines.length === 1 && item.classList.contains('tile')) {
        const primary = item.querySelector('.tile-primary');
        const labels = {
          on: 'on', off: 'off', present: 'present', 'not-present': 'not present',
          active: 'active', inactive: 'inactive', open: 'open', closed: 'closed',
          locked: 'locked', unlocked: 'unlocked', wet: 'wet', dry: 'dry',
          unknown: 'Unknown',
        };
        const states = primary
          ? Object.keys(labels).filter((state) => primary.classList.contains(state))
          : [];
        if (states.length === 1) cleanedLines.push(labels[states[0]]);
      }
      if (cleanedLines.length !== 1) {
        if (cleanedLines.length) item.__eyebatStatusLines = cleanedLines;
        return cleanedLines;
      }

      const line = cleanedLines[0];
      const oneLinePatterns = [
        [/^Dashboards\s+(.+)$/i, ['Dashboards', '$1']],
        [/^Modes?\s+(.+)$/i, ['Modes', '$1']],
        [/^Receiver\s+(.+)$/i, ['Receiver', '$1']],
        [/^Weather\s+(.+)$/i, ['Weather', '$1']],
        [/^HSM Status\s+(.+)$/i, ['HSM Status', '$1']],
      ];
      for (const [pattern, replacement] of oneLinePatterns) {
        const match = line.match(pattern);
        if (!match) continue;
        return replacement
          .map((part) => part.replace('$1', match[1]).replace(/\s+/g, ' ').trim())
          .filter(Boolean);
      }
      return cleanedLines;
    }

    function tileVisualStyle(item) {
      for (const el of [item, ...item.querySelectorAll('*')]) {
        const style = window.getComputedStyle(el);
        const backgroundImage = String(style.backgroundImage || '').trim();
        const backgroundColor = String(style.backgroundColor || '').trim();
        const hasImage =
          backgroundImage &&
          backgroundImage !== 'none' &&
          !backgroundImage.includes('gradient(');
        const hasColor =
          backgroundColor &&
          backgroundColor !== 'transparent' &&
          backgroundColor !== 'rgba(0, 0, 0, 0)';
        if (hasImage || hasColor) {
          return {
            backgroundImage: hasImage ? backgroundImage : '',
            backgroundColor: hasColor ? backgroundColor : '',
          };
        }
      }
      return null;
    }

    function buildStatusCard(item, x, y, width, height, compact = false) {
      const lines = statusLinesForItem(item);
      if (!lines.length) return null;

      const isDashboardLink = lines[0].toLowerCase() === 'dashboards' && lines.length > 1;
      const titleText = isDashboardLink ? lines.slice(1).join(' ') : lines[0];
      const values = [];
      for (const line of lines.slice(1)) {
        if (values.length && /:\s*$/.test(values[values.length - 1])) values[values.length - 1] += ' ' + line;
        else values.push(line);
      }
      const detailText = isDashboardLink ? 'Dashboard' : values.join('\n') || 'State unavailable';
      const visualStyle = tileVisualStyle(item);
      const dense = width < 400 || height < 220;
      const short = height < 120;
      const longDetail = compact && detailText.length > 100;

      const card = document.createElement('div');
      card.style.setProperty('position', 'absolute', 'important');
      card.style.setProperty('left', `${x}px`, 'important');
      card.style.setProperty('top', `${y}px`, 'important');
      card.style.setProperty('width', `${width}px`, 'important');
      card.style.setProperty('height', `${height}px`, 'important');
      card.style.setProperty('box-sizing', 'border-box', 'important');
      card.style.setProperty('padding', short ? '8px 12px' : compact || dense ? '12px 16px' : '26px 30px', 'important');
      card.style.setProperty('border-radius', compact ? '8px' : '16px', 'important');
      card.style.setProperty('border', '1px solid rgba(148, 163, 184, 0.34)', 'important');
      card.style.setProperty(
        'box-shadow',
        compact
          ? 'inset 4px 0 0 #38bdf8, 0 10px 28px rgba(0, 0, 0, 0.18)'
          : 'inset 6px 0 0 #38bdf8, 0 18px 50px rgba(0, 0, 0, 0.22)',
        'important'
      );
      if (visualStyle && visualStyle.backgroundImage) {
        card.style.setProperty(
          'background-image',
          `linear-gradient(rgba(9, 15, 25, 0.62), rgba(9, 15, 25, 0.80)), ${visualStyle.backgroundImage}`,
          'important'
        );
        card.style.setProperty('background-size', 'cover', 'important');
        card.style.setProperty('background-position', 'center', 'important');
      } else if (visualStyle && visualStyle.backgroundColor) {
        card.style.setProperty(
          'background',
          `linear-gradient(135deg, rgba(9, 15, 25, 0.86), rgba(23, 37, 54, 0.94)), ${visualStyle.backgroundColor}`,
          'important'
        );
      } else {
        card.style.setProperty(
          'background',
          'linear-gradient(135deg, #101a26, #172536)',
          'important'
        );
      }
      card.style.setProperty('color', '#e8eef6', 'important');
      card.style.setProperty('overflow', 'hidden', 'important');
      card.style.setProperty('display', 'flex', 'important');
      card.style.setProperty('flex-direction', 'column', 'important');
      card.style.setProperty('justify-content', 'center', 'important');
      card.style.setProperty('gap', short ? '4px' : compact || dense ? '7px' : '18px', 'important');

      const title = document.createElement('div');
      title.textContent = titleText;
      title.style.setProperty(
        'font',
        compact
          ? (short ? '700 18px/1.12 sans-serif' : '700 23px/1.12 sans-serif')
          : dense ? '700 26px/1.15 sans-serif' : '700 clamp(26px, 2.3vw, 38px)/1.1 sans-serif',
        'important'
      );
      title.style.setProperty('flex-shrink', '0', 'important');
      title.style.setProperty('letter-spacing', '0', 'important');
      title.style.setProperty('white-space', 'normal', 'important');
      title.style.setProperty('overflow-wrap', 'anywhere', 'important');
      title.style.setProperty('display', '-webkit-box', 'important');
      title.style.setProperty('-webkit-line-clamp', height < 100 ? '1' : '2', 'important');
      title.style.setProperty('-webkit-box-orient', 'vertical', 'important');
      title.style.setProperty('overflow', 'hidden', 'important');
      title.style.setProperty('text-overflow', 'ellipsis', 'important');
      card.appendChild(title);

      const details = document.createElement('div');
      details.textContent = detailText;
      details.style.setProperty(
        'font',
        compact
          ? (short || longDetail ? '500 18px/1.25 sans-serif' : '500 22px/1.25 sans-serif')
          : dense ? '500 24px/1.3 sans-serif' : '500 clamp(20px, 1.8vw, 30px)/1.45 sans-serif',
        'important'
      );
      details.style.setProperty('color', '#dbe7f4', 'important');
      details.style.setProperty('white-space', 'pre-line', 'important');
      details.style.setProperty('overflow', 'hidden', 'important');
      details.style.setProperty('display', '-webkit-box', 'important');
      details.style.setProperty('-webkit-line-clamp', short ? '2' : longDetail ? '4' : compact ? '3' : '5', 'important');
      details.style.setProperty('-webkit-box-orient', 'vertical', 'important');
      const incidentActive = /(?:incident|leak|flood|alarm)/i.test(titleText) &&
        /^(active|on|wet|detected)$/i.test(detailText.trim());
      if (incidentActive || /^(wet|state unavailable|unknown)$/i.test(detailText.trim())) {
        details.style.setProperty('color', '#fde68a', 'important');
        card.style.setProperty('box-shadow', 'inset 5px 0 0 #fbbf24', 'important');
      } else if (/^(active|on|open)$/i.test(detailText.trim())) {
        details.style.setProperty('color', '#6ee7b7', 'important');
        card.style.setProperty('box-shadow', 'inset 5px 0 0 #34d399', 'important');
      } else if (/^(inactive|off|closed)$/i.test(detailText.trim())) {
        card.style.setProperty('box-shadow', 'inset 4px 0 0 #64748b', 'important');
      }
      card.appendChild(details);
      return card;
    }

    function buildStatusOnlyCard(item, x, y, width, height) {
      return buildStatusCard(item, x, y, width, height, false);
    }

    function buildCompactStatusCard(item, x, y, width, height) {
      return buildStatusCard(item, x, y, width, height, true);
    }

    const hiddenItems = new Set();
    const statusItems = [];
    const seenStatusKeys = new Set();
    for (const item of selectedItems) {
      if (imageItems.includes(item)) continue;
      const text = statusLinesForItem(item).join('\n');
      const lower = text.toLowerCase();
      const className = String(item.className || '').toLowerCase();
      const unsupportedCamera = lower.includes(':(') && lower.includes('eufy ');
      const visualClockOnly = className.includes('clocktile');
      const statusKey = statusLinesForItem(item).join('|').toLowerCase();
      if (!text || unsupportedCamera || visualClockOnly || seenStatusKeys.has(statusKey)) {
        item.style.setProperty('display', 'none', 'important');
        hiddenItems.add(item);
        continue;
      }
      seenStatusKeys.add(statusKey);
      statusItems.push(item);
    }

    // Allocate the whole kiosk canvas using actual, deduplicated tile counts.
    // Dense sensor walls get more columns so camera views keep half the screen.
    const viewportHeight = window.innerHeight || 1080;
    const statusOnly = !imageItems.length;
    const maxImageColumns = viewportWidth >= 1400 ? 4 : viewportWidth >= 900 ? 3 : viewportWidth >= 620 ? 2 : 1;
    const imageColumns = Math.max(1, Math.min(maxImageColumns,
      imageItems.length <= 4 ? Math.min(2, imageItems.length) : imageItems.length <= 6 || imageItems.length === 9 ? 3 : maxImageColumns));
    const imageRows = Math.ceil(imageItems.length / imageColumns);
    const hasLongStatus = statusItems.some((item) => statusLinesForItem(item).slice(1).join(' ').length > 100);
    const maxStatusColumns = viewportWidth >= 1400
      ? statusItems.length > 30 ? 8 : statusItems.length > 18 ? 6 : statusOnly || hasLongStatus ? 4 : 5
      : viewportWidth >= 900 ? 4 : viewportWidth >= 620 ? 2 : 1;
    const statusColumns = Math.max(1, Math.min(maxStatusColumns, statusItems.length));
    const statusRows = Math.ceil(statusItems.length / statusColumns);
    const statusBudget = statusOnly ? viewportHeight : Math.min(viewportHeight * 0.5, statusRows * 138);
    const imageHeight = Math.floor((viewportHeight - statusBudget - gap * (imageRows + statusRows + 1)) / Math.max(1, imageRows));
    const statusTop = gap + imageRows * (imageHeight + gap);
    const statusHeight = Math.floor((viewportHeight - statusTop - gap * statusRows) / Math.max(1, statusRows));
    function rowBox(index, count, columns) {
      const row = Math.floor(index / columns);
      const rowCount = Math.min(columns, count - row * columns);
      const width = Math.floor((viewportWidth - gap * (rowCount + 1)) / rowCount);
      return {width, x: gap + (index % columns) * (width + gap), row};
    }

    // Keep capture stages outside the hub's reactive grid. Its fixed widths
    // and rerenders otherwise clip tiles or replace the composed dashboard.
    const layoutRoot = document.body;
    function prepareCaptureCanvas(root) {
      for (const el of [document.documentElement, document.body]) {
        el.style.setProperty('margin', '0', 'important');
        el.style.setProperty('padding', '0', 'important');
        el.style.setProperty('background', '#0f172a', 'important');
        el.style.setProperty('overflow-x', 'hidden', 'important');
        el.style.setProperty('overflow-y', 'hidden', 'important');
      }
      for (const el of document.querySelectorAll('#app, .v-application, .v-application--wrap')) {
        el.style.setProperty('background', '#0f172a', 'important');
      }
      const chromeSelectors = [
        '.navbar',
        '.top-bar',
        '.toolbar',
        '.dashboard-header',
        '.dashboardHeader',
        '[class*="dashboard-header"]',
        '[class*="DashboardHeader"]',
        '[class*="dashboard-menu"]'
      ];
      const forceChromeSelectors = [
        'header',
        'nav',
        '[role="banner"]',
        '.v-toolbar',
        '.v-app-bar',
        '.md-toolbar',
        '.dashboard > .header',
        '.header.flex',
        '.dashboard-header',
        '.dashboardHeader',
        '[class*="dashboard-header"]',
        '[class*="DashboardHeader"]'
      ];
      for (const selector of forceChromeSelectors) {
        for (const el of document.querySelectorAll(selector)) {
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('visibility', 'hidden', 'important');
          el.style.setProperty('height', '0', 'important');
          el.style.setProperty('min-height', '0', 'important');
          el.style.setProperty('overflow', 'hidden', 'important');
        }
      }
      for (const selector of chromeSelectors) {
        for (const el of document.querySelectorAll(selector)) {
          if (root.contains(el)) continue;
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('visibility', 'hidden', 'important');
          el.style.setProperty('height', '0', 'important');
          el.style.setProperty('min-height', '0', 'important');
          el.style.setProperty('overflow', 'hidden', 'important');
        }
      }
      root.style.setProperty('margin', '0', 'important');
      root.style.setProperty('padding', '0', 'important');
      root.style.setProperty('top', '0', 'important');
      root.style.setProperty('width', '100%', 'important');
      root.style.setProperty('max-width', '100%', 'important');
      root.style.setProperty('overflow', 'hidden', 'important');
    }
    prepareCaptureCanvas(layoutRoot);
    layoutRoot.style.setProperty('position', 'relative', 'important');
    let imageStage = document.getElementById('eyebat-hubitat-visual-stage');
    if (!imageStage) {
      imageStage = document.createElement('div');
      imageStage.id = 'eyebat-hubitat-visual-stage';
      layoutRoot.prepend(imageStage);
    }
    const previousImages = [...imageStage.querySelectorAll('img')];
    imageStage.innerHTML = '';
    imageStage.style.setProperty('position', 'absolute', 'important');
    imageStage.style.setProperty('left', '0', 'important');
    imageStage.style.setProperty('top', '0', 'important');
    imageStage.style.setProperty('width', '100%', 'important');
    imageStage.style.setProperty('z-index', '20', 'important');
    imageStage.style.setProperty('pointer-events', 'none', 'important');

    imageItems.forEach((item, index) => {
      let src = imageSourceForItem(item);
      if (!src) return;
      // Avoid nesting the source's generated caption inside the dashboard.
      const cleanSource = new URL(src, window.location.href);
      if (cleanSource.pathname.startsWith('/last_screenshot/')) {
        cleanSource.pathname = cleanSource.pathname.replace('/last_screenshot/', '/clean_screenshot/');
        src = cleanSource.href;
      }
      item.style.setProperty('display', 'none', 'important');

      const {width: imageWidth, x, row} = rowBox(index, imageItems.length, imageColumns);
      const y = gap + row * (imageHeight + gap);
      const label = imageLabelForItem(item, src);

      const frame = document.createElement('div');
      frame.style.setProperty('position', 'absolute', 'important');
      frame.style.setProperty('left', `${x}px`, 'important');
      frame.style.setProperty('top', `${y}px`, 'important');
      frame.style.setProperty('width', `${imageWidth}px`, 'important');
      frame.style.setProperty('height', `${imageHeight}px`, 'important');
      frame.style.setProperty('overflow', 'hidden', 'important');
      frame.style.setProperty('border-radius', '8px', 'important');
      frame.style.setProperty('box-sizing', 'border-box', 'important');
      frame.style.setProperty('border', '1px solid rgba(148, 163, 184, 0.34)', 'important');
      frame.style.setProperty('background', '#0f172a', 'important');

      const clone = previousImages[index] || document.createElement('img');
      if (clone.src !== src) clone.src = src;
      clone.alt = label;
      clone.style.setProperty('display', 'block', 'important');
      clone.style.setProperty('width', '100%', 'important');
      clone.style.setProperty('height', 'calc(100% - 66px)', 'important');
      clone.style.setProperty('object-fit', 'contain', 'important');
      clone.style.setProperty('margin', '0', 'important');
      frame.appendChild(clone);

      const badge = document.createElement('div');
      const cameraTitle = document.createElement('div');
      cameraTitle.textContent = label;
      cameraTitle.style.cssText = 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
      badge.appendChild(cameraTitle);
      const sourceParts = new URL(src, window.location.href).pathname.split('/').filter(Boolean);
      const sourceIndex = sourceParts.findIndex((part) => ['last_screenshot', 'clean_screenshot', 'embedded_screenshot', 'screenshots'].includes(part));
      const cameraName = sourceIndex >= 0 ? decodeURIComponent(sourceParts[sourceIndex + 1] || '') : '';
      const health = cameraHealth[cameraName] || {};
      if (health) {
        const rawStamp = String(health.captured || '').replace(' ', 'T');
        const stamp = Date.parse(rawStamp && !/(Z|[+-]\d\d:\d\d)$/.test(rawStamp) ? rawStamp + 'Z' : rawStamp);
        const minutes = Number.isFinite(stamp) ? Math.max(0, Math.floor((Date.now() - stamp) / 60000)) : null;
        const age = minutes === null ? 'age unknown' : minutes < 1 ? 'just now' : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m ago` : `${Math.floor(minutes / 1440)}d ago`;
        const overdue = minutes !== null && minutes > Math.max(60, Number(health.frequency || 30) * 3);
        const state = !Number.isFinite(stamp) ? 'Saved image' : health.failed ? 'Capture failed · saved image' : String(health.message || '').includes('source_checked_unchanged') ? 'Source unchanged' : overdue ? 'Capture overdue' : 'Captured';
        const ageLine = document.createElement('span');
        ageLine.textContent = `${state} · ${age}`;
        ageLine.style.setProperty('display', 'block', 'important');
        ageLine.style.setProperty('font', '500 clamp(13px, 0.9vw, 17px)/1.25 sans-serif', 'important');
        ageLine.style.setProperty('margin-top', '3px', 'important');
        badge.appendChild(ageLine);
        if (health.failed || overdue || minutes === null) {
          badge.style.setProperty('border-left', '5px solid #fbbf24', 'important');
          ageLine.style.setProperty('color', '#fde68a', 'important');
        }
      }
      badge.style.setProperty('position', 'absolute', 'important');
      badge.style.setProperty('left', '0', 'important');
      badge.style.setProperty('bottom', '0', 'important');
      badge.style.setProperty('width', '100%', 'important');
      badge.style.setProperty('height', '66px', 'important');
      badge.style.setProperty('box-sizing', 'border-box', 'important');
      badge.style.setProperty('padding', '7px 10px', 'important');
      badge.style.setProperty('background', 'rgba(15, 23, 42, 0.78)', 'important');
      badge.style.setProperty('color', '#f8fafc', 'important');
      badge.style.setProperty('font', '700 clamp(18px, 1.25vw, 24px)/1.2 sans-serif', 'important');
      badge.style.setProperty('white-space', 'pre-line', 'important');
      badge.style.setProperty('overflow', 'hidden', 'important');
      badge.style.setProperty('text-overflow', 'ellipsis', 'important');
      frame.appendChild(badge);
      imageStage.appendChild(frame);
    });

    let statusStage = document.getElementById('eyebat-hubitat-status-stage');
    if (!statusStage) {
      statusStage = document.createElement('div');
      statusStage.id = 'eyebat-hubitat-status-stage';
      layoutRoot.prepend(statusStage);
    }
    statusStage.innerHTML = '';
    statusStage.style.setProperty('position', 'absolute', 'important');
    statusStage.style.setProperty('left', '0', 'important');
    statusStage.style.setProperty('top', '0', 'important');
    statusStage.style.setProperty('width', '100%', 'important');
    statusStage.style.setProperty('z-index', '15', 'important');
    statusStage.style.setProperty('pointer-events', 'none', 'important');

    statusItems.forEach((item, index) => {
      const {width: statusWidth, x, row} = rowBox(index, statusItems.length, statusColumns);
      const y = statusTop + row * (statusHeight + gap);
      if (statusOnly) {
        const card = buildStatusOnlyCard(item, x, y, statusWidth, statusHeight);
        item.style.setProperty('display', 'none', 'important');
        hiddenItems.add(item);
        if (card) statusStage.appendChild(card);
      } else {
        const card = buildCompactStatusCard(item, x, y, statusWidth, statusHeight);
        item.style.setProperty('display', 'none', 'important');
        hiddenItems.add(item);
        if (card) statusStage.appendChild(card);
      }
    });

    const totalHeight = statusTop + statusRows * (statusHeight + gap) + gap;
    const layout = document.querySelector('.vgl-layout');
    if (layout) {
      layout.style.setProperty('height', `${totalHeight}px`, 'important');
      layout.style.setProperty('max-width', 'none', 'important');
      layout.style.setProperty('width', '100%', 'important');
    }
    const containers = [
      document.getElementById('divDashboardTopLevelContainer'),
      document.querySelector('[id^="dashboardContainer_"]'),
      document.querySelector('.dashboard'),
      document.querySelector('.wrapper'),
      layoutRoot,
      document.body,
    ];
    for (const container of containers) {
      if (!container) continue;
      container.style.setProperty('min-height', `${Math.max(totalHeight, window.innerHeight || 0)}px`, 'important');
      container.style.setProperty('width', '100%', 'important');
      container.style.setProperty('max-width', '100%', 'important');
      container.style.setProperty('overflow', 'hidden', 'important');
    }

    return {hidden: hiddenItems.size, images: imageItems.length, statuses: statusItems.length};
  }

  const result = applyEyebatHubitatLayout();
  if (window.__eyebatHubitatLayoutTimer) {
    window.clearInterval(window.__eyebatHubitatLayoutTimer);
  }
  let remainingPasses = 30;
  window.__eyebatHubitatLayoutTimer = window.setInterval(() => {
    applyEyebatHubitatLayout();
    remainingPasses -= 1;
    if (remainingPasses <= 0) {
      window.clearInterval(window.__eyebatHubitatLayoutTimer);
      window.__eyebatHubitatLayoutTimer = null;
    }
  }, 100);
  return result;
})();
"""


def _apply_hubitat_cloud_dashboard_visual_cleanup(driver, name: str) -> dict[str, int]:
    """Make Hubitat cloud dashboard screenshots visual-first for Eyebat capture.

    Hubitat Dashboard v2 can render newly authorized Virtual Image devices as
    default 1x1 tiles even after the dashboard state is saved. This cleanup is
    capture-side only: it expands real Eyebat image tiles and moves status
    cards underneath without changing the hub's persisted dashboard state.
    """

    try:
        # Match the physical kiosks, including the content viewport rather than
        # Chrome's outer window (whose browser chrome otherwise removes pixels).
        if getattr(driver, "_eyebat_kiosk_viewport", False) is not True:
            try:
                driver.execute_cdp_cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": 1920,
                        "height": 1080,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                driver._eyebat_kiosk_viewport = True
            except Exception:
                pass
        from app.utils.template_manager import get_templates

        health = {
            key: {
                "captured": template.get("last_screenshot_time"),
                "frequency": template.get("frequency"),
                "failed": bool(template.get("capture_failed")),
                "message": template.get("last_capture_message"),
            }
            for key, template in get_templates().items()
        }
        raw = driver.execute_script(
            _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT,
            health,
            name,
            {
                camera: label
                for camera, label in capture_policy.CAPTURE_POLICY.get(
                    "dashboard_camera_labels", {}
                ).items()
                if camera in health
            },
        )
    except Exception as exc:
        logging.debug("[%s] Hubitat dashboard visual cleanup failed: %s", name, exc)
        return {"hidden": 0, "images": 0, "statuses": 0}
    if not isinstance(raw, dict):
        return {"hidden": 0, "images": 0, "statuses": 0}
    return {
        "hidden": int(raw.get("hidden") or 0),
        "images": int(raw.get("images") or 0),
        "statuses": int(raw.get("statuses") or 0),
    }


def _settle_hubitat_dashboard_for_capture(driver, name):
    """Preserve decoded tiles and wait for remaining images before a snapshot."""
    deadline = time.monotonic() + 8
    layout = _apply_hubitat_cloud_dashboard_visual_cleanup(driver, name)
    while not (layout["images"] or layout["statuses"]) and time.monotonic() < deadline:
        time.sleep(0.25)
        layout = _apply_hubitat_cloud_dashboard_visual_cleanup(driver, name)
    driver.execute_script(
        "window.clearInterval(window.__eyebatHubitatLayoutTimer);"
        "window.__eyebatHubitatLayoutTimer = null;"
    )
    # A loading shell or a replaced tile tree must not become the latest image.
    if not (layout["images"] or layout["statuses"]):
        raise TimeoutException("Hubitat dashboard tiles were not ready for capture")
    while time.monotonic() < deadline:
        ready = driver.execute_script(
            "return [...document.querySelectorAll('#eyebat-hubitat-visual-stage img')]"
            ".every(img => img.complete);"
        )
        if ready:
            break
        time.sleep(0.2)
    if driver.execute_script(
        "const images = [...document.querySelectorAll('#eyebat-hubitat-visual-stage img')];"
        "return images.length > 0 && images.every(img => !img.complete || !img.naturalWidth);"
    ):
        raise TimeoutException("Hubitat dashboard camera images were unavailable")
    # A bad child URL must not masquerade as a loaded picture or hide other tiles.
    driver.execute_script(
        "for (const img of document.querySelectorAll('#eyebat-hubitat-visual-stage img')) {"
        "if (!img.complete || !img.naturalWidth) {"
        "const badge = img.parentElement.querySelector('div');"
        "if (badge) { const status = badge.querySelector('span') || document.createElement('span');"
        "status.textContent = 'Image unavailable';"
        "status.style.cssText = 'display:block;color:#fbbf24;font-size:18px';"
        "badge.appendChild(status); } } }"
    )


def _hubitat_cloud_dashboard_error_reason(
    driver, url: str | None, name: str | None
) -> str:
    """Return a capture-failure reason for known Hubitat cloud error pages."""

    if not (
        _is_hubitat_cloud_dashboard_url(url)
        or str(name or "").strip().lower().startswith("hubitat")
    ):
        return ""

    try:
        raw = driver.execute_script("""
            const text = String(
              (document.body && (document.body.innerText || document.body.textContent)) || ''
            ).replace(/\\s+/g, ' ').trim().toLowerCase();
            return {
              text,
              dashboardItems: document.querySelectorAll([
                '.vgl-item[data-tour^="DashboardItem_"]',
                '[data-tour^="DashboardItem_"]',
                '[data-testid^="DashboardItem_"]',
                '[id^="DashboardItem_"]',
                '.react-grid-item',
                '.grid-stack-item',
              ].join(',')).length,
              images: document.querySelectorAll([
                "img[src*='last_screenshot']",
                "img[src*='clean_screenshot']",
                "img[src*='embedded_screenshot']",
                "img[src*='/screenshots/']",
                "img[src*='latest_camera']",
                '#eyebat-hubitat-visual-stage > div',
              ].join(',')).length,
            };
            """)
    except Exception as exc:
        logging.debug("[%s] Hubitat error-page text check failed: %s", name, exc)
        return ""

    if isinstance(raw, str):
        text = raw
        dashboard_items = 0
        images = 0
    elif isinstance(raw, dict):
        text = str(raw.get("text") or "")
        dashboard_items = int(raw.get("dashboardItems") or 0)
        images = int(raw.get("images") or 0)
    else:
        return ""

    text = text.lower()
    if "no response from hub" in text:
        return "hubitat_no_response_from_hub"
    if "gateway timeout" in text and "hub" in text:
        return "hubitat_gateway_timeout"
    # Navigation buttons have rounded styling too; they are not dashboard content.
    if not text.strip() and dashboard_items == 0 and images == 0:
        return "hubitat_blank_dashboard"
    return ""


def _has_specific_hubitat_preflight_reason(url: str | None) -> bool:
    """Return whether ``url`` already has a more useful Hubitat failure reason."""

    entry = throttle_cache.get(url) if url else None
    if not isinstance(entry, dict):
        return False
    return str(entry.get("reason") or "") in HUBITAT_CLOUD_DASHBOARD_FAILURE_REASONS


def _purge_driver_cache():
    """Reset caches after driver errors or Chrome updates.

    Both undetected-chromedriver and webdriver_manager caches
    are cleared so the active tool fetches a matching driver.
    """
    # uc driver path: ~/.local/share/undetected_chromedriver
    # wdm driver path: ~/.wdm

    uc_cache_dir = os.path.expanduser("~/.local/share/undetected_chromedriver")
    if os.path.isdir(uc_cache_dir):
        logging.info(f"Removing undetected_chromedriver cache: {uc_cache_dir}")
        time.sleep(1)
        shutil.rmtree(uc_cache_dir, ignore_errors=True)

    # If you're using webdriver_manager:
    wdm_cache_dir = os.path.expanduser("~/.wdm")
    if os.path.isdir(wdm_cache_dir):
        logging.info(f"Removing webdriver_manager cache: {wdm_cache_dir}")
        shutil.rmtree(wdm_cache_dir, ignore_errors=True)


def capture_screenshot_phantom(
    url,
    output_path,
    timeout=10,
    name="unknown",
    invert=False,
    dark=False,
    stabilize_mode="off",
    above_fold_only=True,
    popup_xpath=None,
    dedicated_selector=None,
    viewport_width=1920,
    viewport_height=1080,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36"
    ),
):
    import logging
    import os
    import shutil
    import subprocess

    if shutil.which("phantomjs") is None:
        logging.warning("PhantomJS not found; cannot capture screenshot.")
        return False

    clean_url = sanitize_url(url)
    if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        url = "https://" + url

    timeout = max(timeout, 15)
    timeout = int(timeout)

    # Safely escape backslashes and quotes in XPaths
    safe_popup_xpath = ""
    safe_dedicated_selector = ""
    if popup_xpath:
        safe_popup_xpath = popup_xpath.replace("\\", "\\\\").replace('"', '\\"')
    if dedicated_selector:
        safe_dedicated_selector = dedicated_selector.replace("\\", "\\\\").replace(
            '"', '\\"'
        )

    remove_popup_script = ""
    if popup_xpath:
        remove_popup_script = f"""
            page.evaluate(function() {{
                var snapshot = document.evaluate("{safe_popup_xpath}", document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                for (var i = 0; i < snapshot.snapshotLength; i++) {{
                    var node = snapshot.snapshotItem(i);
                    if (node && node.parentNode) {{
                        node.parentNode.removeChild(node);
                    }}
                }}
            }});
        """

    dedicated_selector_script = ""
    if dedicated_selector:
        dedicated_selector_script = f"""
            var rect = page.evaluate(function() {{
                var el = document.evaluate("{safe_dedicated_selector}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!el) return null;
                var b = el.getBoundingClientRect();
                return {{
                    top: b.top,
                    left: b.left,
                    width: b.width,
                    height: b.height
                }};
            }});
            if (rect) {{
                page.clipRect = rect;
            }}
        """

    tmpdir = f"/tmp/glimpser_{name}"
    os.makedirs(tmpdir, exist_ok=True)
    if os.path.exists(tmpdir):  # check if writeable too...
        # Paths for the one-off PhantomJS script and its output
        script_path = os.path.join(tmpdir, "capture.js")
        screenshot_tmp = os.path.join(tmpdir, "phantom_out.png")

        phantom_script = f"""
            var page = require('webpage').create();
            page.settings.ignoreSslErrors = true;
            page.settings.sslProtocol = 'any';
            page.settings.userAgent = "{user_agent}";
            page.settings.loadImages = true;
            page.settings.resourceTimeout = 55000;
            page.viewportSize = {{
                width: {viewport_width},
                height: {viewport_height}
            }};
            if ({str(above_fold_only).lower()}) {{
                page.clipRect = {{
                    top: 0,
                    left: 0,
                    width: {viewport_width},
                    height: {viewport_height}
                }};
            }}

            function waitForImages(callback) {{
                var startTime = Date.now();
                var maxWaitTime = 20000;
                function checkImages() {{
                    var ready = page.evaluate(function() {{
                        var imgs = document.images;
                        for (var i=0; i<imgs.length;i++) {{
                            if(!imgs[i].complete) return false;
                        }}
                        return true;
                    }});
                    if(ready || (Date.now() - startTime) >= maxWaitTime) {{
                        callback();
                    }} else {{
                        setTimeout(checkImages, 500);
                    }}
                }}
                checkImages();
            }}

            page.open("{url}", function(status) {{
                if (status !== 'success') {{
                    page.render("{screenshot_tmp}");
                    phantom.exit(0);
                }} else {{
                    {remove_popup_script}
                    waitForImages(function() {{
                        setTimeout(function() {{
                            {dedicated_selector_script}
                            page.render("{screenshot_tmp}");
                            phantom.exit(0);
                        }}, 2000);
                    }});
                }}
            }});
        """

        # Write the generated script so PhantomJS can execute it
        with open(script_path, "w") as f:
            f.write(phantom_script)

        # Invoke PhantomJS with relaxed security to render the page
        try:
            subprocess.run(
                [
                    "phantomjs",
                    "--ignore-ssl-errors=true",
                    "--ssl-protocol=any",
                    "--web-security=false",
                    script_path,
                ],
                timeout=timeout + 10,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logging.warning(f"PhantomJS timed out for {clean_url}.")
            return False
        except Exception as e:
            logging.warning(f"PhantomJS error for {clean_url}: {e}")
            return False

        if not os.path.exists(screenshot_tmp):
            logging.warning(
                f"PhantomJS script completed but no screenshot found for {clean_url}"
            )
            return False

        try:
            return _finalize_screenshot(
                screenshot_tmp,
                output_path,
                name=name,
                invert=invert,
                dark=dark,
                stabilize_mode=stabilize_mode,
                url=url,
                clean_url=clean_url,
            )
        except Exception as e:
            logging.error(
                f"Error post-processing Phantom screenshot for {clean_url}: {e}"
            )
            return False


def cleanup_old_tempdirs(prefix="glimpser_", max_age_hours=12):
    """
    Best-effort removal of leftover ephemeral directories older than `max_age_hours`.
    Use the same temporary root as captures, including an operator-set TMPDIR.
    """
    now = time.time()
    tmp_root = tempfile.gettempdir()
    for entry in os.scandir(tmp_root):
        if entry.is_dir() and entry.name.startswith(prefix):
            dir_path = os.path.join(tmp_root, entry.name)
            try:
                st = os.stat(dir_path)
                # If older than max_age_hours, remove it
                if (now - st.st_mtime) > (max_age_hours * 3600):
                    logging.info(f"Removing stale temp directory: {dir_path}")
                    shutil.rmtree(dir_path, ignore_errors=True)
            except Exception as e:
                logging.debug(f"Could not remove {dir_path}: {e}")


def cleanup_orphaned_browser_processes(
    max_age_seconds: int = _ORPHAN_BROWSER_MAX_AGE_SECONDS,
    force: bool = False,
) -> int:
    """Reap stale Chrome trees left behind after crashed Selenium captures.

    The cleanup is intentionally narrow: only orphaned ``chromedriver`` root
    processes adopted by PID 1 are eligible. Active captures are parented by the
    current worker process, so this avoids killing a capture that is in flight.
    """

    global _ORPHAN_BROWSER_CLEANUP_LAST

    now = time.time()
    interval = max(0, int(_ORPHAN_BROWSER_CLEANUP_INTERVAL_SECONDS))
    if not force and interval and (now - _ORPHAN_BROWSER_CLEANUP_LAST) < interval:
        return 0
    _ORPHAN_BROWSER_CLEANUP_LAST = now

    try:
        max_age_seconds = max(0, int(max_age_seconds or 0))
    except (TypeError, ValueError):
        max_age_seconds = _ORPHAN_BROWSER_MAX_AGE_SECONDS

    current_pid = os.getpid()
    stale_roots = []
    for proc in psutil.process_iter(["pid", "ppid", "name", "create_time"]):
        try:
            info = getattr(proc, "info", {}) or {}
            pid = int(info.get("pid") or proc.pid)
            ppid = int(info.get("ppid") or proc.ppid())
            name = str(info.get("name") or proc.name() or "").lower()
            create_time = float(info.get("create_time") or proc.create_time())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except (AttributeError, TypeError, ValueError):
            continue

        if pid == current_pid:
            continue
        if ppid != 1 or "chromedriver" not in name:
            continue
        if (now - create_time) < max_age_seconds:
            continue
        stale_roots.append(proc)

    targets_by_pid = {}
    root_pids = []
    for root in stale_roots:
        try:
            root_pid = int(getattr(root, "info", {}).get("pid") or root.pid)
            root_pids.append(root_pid)
            descendants = root.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            descendants = []
        except (AttributeError, TypeError, ValueError):
            descendants = []

        for proc in [*descendants, root]:
            try:
                pid = int(getattr(proc, "info", {}).get("pid") or proc.pid)
            except (AttributeError, TypeError, ValueError):
                continue
            if pid != current_pid:
                targets_by_pid[pid] = proc

    targets = list(targets_by_pid.values())
    if not targets:
        return 0

    logging.warning(
        "Cleaning up %d stale orphaned browser processes from chromedriver roots %s",
        len(targets),
        sorted(root_pids),
    )

    for proc in targets:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except OSError as exc:
            logging.debug("Failed to terminate stale browser process: %s", exc)

    try:
        _, alive = psutil.wait_procs(targets, timeout=3)
    except (psutil.Error, OSError, ValueError):
        alive = targets

    for proc in alive:
        try:
            if proc.is_running():
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except OSError as exc:
            logging.debug("Failed to kill stale browser process: %s", exc)

    return len(targets)


def _browser_capture_lock_path(kind: str = "default") -> str:
    """Return the cross-process lock path used to serialize Chrome captures.

    SDM WebRTC preview captures use a separate lightweight internal page. Giving
    them their own lock keeps those camera refreshes from starving behind the
    broader browser-render queue for unrelated public pages.
    """

    normalized = str(kind or "default").strip().lower()
    if normalized == "sdm_webrtc":
        return os.getenv(
            "GLIMPSER_WEBRTC_CAPTURE_LOCK",
            os.path.join(tempfile.gettempdir(), "glimpser-webrtc-capture.lock"),
        )
    return os.getenv(
        "GLIMPSER_BROWSER_CAPTURE_LOCK",
        os.path.join(tempfile.gettempdir(), "glimpser-browser-capture.lock"),
    )


def _acquire_browser_capture_file_lock(
    name: str, wait_seconds: float, *, kind: str = "default"
) -> tuple[bool, io.TextIOBase | None]:
    """Acquire the global headless-browser capture slot.

    Scheduler jobs can run in separate worker processes, so a process-local
    semaphore is not enough. A small ``flock`` keeps heavyweight Chrome renders
    serialized across the whole host while allowing non-browser captures to run
    normally.
    """

    lock_path = _browser_capture_lock_path(kind)
    deadline = time.monotonic() + max(0.0, float(wait_seconds or 0.0))
    lock_file = open(lock_path, "a+", encoding="utf-8")
    transferred = False
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logging.warning(
                        "[%s] Browser capture slot busy after %.1fs", name, wait_seconds
                    )
                    return False, None
                time.sleep(min(0.5, remaining))
        # Metadata I/O failures are not lock contention. Until this function
        # hands ownership to its caller, every exit must close the descriptor.
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"pid={os.getpid()} name={name} ts={time.time():.3f}\n")
        lock_file.flush()
        transferred = True
        return True, lock_file
    finally:
        if not transferred:
            try:
                lock_file.close()
            except OSError as exc:
                logging.debug("[%s] Browser lock close failed: %s", name, exc)


def _release_browser_capture_file_lock(
    lock_file: io.TextIOBase | None, name: str
) -> None:
    """Release a file lock acquired by ``_acquire_browser_capture_file_lock``."""

    if lock_file is None:
        return
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        logging.debug("[%s] Browser capture lock release failed: %s", name, exc)
    finally:
        lock_file.close()


########################################
# The "Tough" capture_screenshot_and_har
########################################


def _reject_browser_error_page(driver, url: str, name: str) -> bool:
    """Reject Chrome's own error UI before it can become a camera image."""
    # Use Chrome's structural markers, not page titles or arbitrary body text:
    # legitimate pages can discuss certificate errors and network failures.
    reason = driver.execute_script("""
        const body = document.body;
        const internal = location.protocol === 'chrome-error:';
        const neterror = body && body.classList.contains('neterror') &&
            document.querySelector('#main-frame-error .error-code');
        const interstitial = body && body.classList.contains('ssl') &&
            document.querySelector('.interstitial-wrapper') &&
            document.querySelector('#error-code, .error-code');
        return internal || neterror || interstitial ? 'browser_error_page' : '';
        """)
    if reason != "browser_error_page":
        return False
    logging.warning("[%s] Rejecting browser error page: %s", name, sanitize_url(url))
    record_preflight_backoff(url, reason, PREFLIGHT_BACKOFF_BROWSER_FAIL)
    return True


def capture_screenshot_and_har(
    url: str,
    output_path: str,
    timeout: int = 30,
    name: str = "unknown",
    popup_xpath: str = None,
    dedicated_selector: str = None,
    invert: bool = False,
    proxy: str = None,
    headless: bool = True,
    stealth: bool = True,
    dark: bool = False,
    danger: bool = False,
    # If you want to store the captured HAR logs:
    har_output_path: str = None,
    stabilize_mode: str = "off",
    allow_sparse_capture: bool = False,
) -> bool:
    """
    Captures a screenshot of `url` and saves to `output_path`.

    1) Danger Mode (danger=True):
       - Attaches to an existing Chrome with the configured remote-debugging
         port.
       - Opens a new tab, loads page, screenshots, closes tab.
       - Skips if the user is active (check_user_activity).
       - Not headless (relies on the user’s Chrome).

    2) Non-Danger Mode (danger=False):
       - ALWAYS uses headless Chrome. No pop-up window on screen.
       - If `stealth` is True and `undetected_chromedriver` is available, it tries to reduce detection of headless.
       - Creates a fresh temporary Chrome user-data-dir.
       - Quits after capture.

    Returns True on success, False otherwise.
    """

    proxy = validate_proxy(proxy)

    # Quick sanity check
    clean_url = sanitize_url(url)
    browser_profile = _browser_capture_profile(clean_url, name)
    is_sdm_webrtc_preview = "/integrations/google/webrtc/preview" in clean_url
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        logging.error(
            f"[capture_screenshot_and_har] Not a valid http/https URL: {clean_url}"
        )
        return False

    if not is_system_online():
        logging.warning("System offline; skipping capture for %s", clean_url)
        return False

    # SDM WebRTC preview captures are internal and should fail fast; a 30s
    # floor causes long queue buildup when several cameras are unreachable.
    if is_sdm_webrtc_preview:
        timeout = max(12, min(int(timeout or 0), 18))
    else:
        timeout = max(timeout, int(browser_profile.get("timeout_floor") or 30))

    cleanup_old_tempdirs(prefix="glimpser_", max_age_hours=12)
    cleanup_orphaned_browser_processes()

    chrome_path = get_chrome_path()
    if chrome_path is None or not os.path.exists(chrome_path):
        _record_renderer_failure("headless", "chrome_missing")
        return False

    # We'll do a partial screenshot path first
    partial_screenshot = output_path + ".tmp.png"
    success = False

    ############
    # Danger Mode
    ############
    if danger and config.get_setting("DANGER_MODE", "True") == "True":
        # If we rely on the user's local Chrome with the debugging port open,
        # confirm it is actually reachable.
        if not is_chrome_debug_port_open("127.0.0.1", config.DANGER_PORT):
            logging.warning(
                "[capture_screenshot_and_har] Danger mode requested, but no Chrome on configured port."
            )
            danger = False
        elif danger:
            status = _danger_session_status()
            if status:
                _maybe_log_danger_session(status, clean_url)

        # Optionally, skip if we detect user activity (like your `check_user_activity`).
        # from app.utils.screenshots import check_user_activity
        if danger and check_user_activity(timeout=10):
            # print("skipping danger mode", name)
            logging.warning(
                "User is active; skipping Danger screenshot to avoid messing with user’s browser."
            )
            danger = False

        # print("not skipping danger mode", name)
        if danger:
            return _capture_danger_mode(
                url,
                partial_screenshot,
                popup_xpath,
                dedicated_selector,
                timeout,
                name,
                invert,
                dark,
            ) and _finalize_screenshot(
                partial_screenshot,
                output_path,
                name,
                invert,
                dark,
                stabilize_mode=stabilize_mode,
                url=url,
                clean_url=clean_url,
                allow_sparse_capture=allow_sparse_capture,
            )

    ##################
    # Non-Danger Mode
    # Non-danger captures must never open a visible browser window.
    headless = True
    ##################
    user_data_dir = None
    driver = None
    browser_lock_file = None
    try:
        if is_sdm_webrtc_preview:
            lock_wait_seconds = min(25.0, max(10.0, float(timeout or 0) + 4.0))
            lock_kind = "sdm_webrtc"
        else:
            lock_wait_seconds = 2.0  # Busy browsers must not occupy capture workers.
            lock_kind = "default"
        lock_acquired, browser_lock_file = _acquire_browser_capture_file_lock(
            name,
            lock_wait_seconds,
            kind=lock_kind,
        )
        if not lock_acquired:
            # Local contention is retried by the durable browser queue; it is
            # not a source failure and must not quarantine an otherwise good URL.
            return CAPTURE_STALE_BROWSER_SLOT_BUSY

        # Create unique ephemeral profile dir in /tmp
        tmp_profile = tempfile.mkdtemp(prefix="glimpser_")
        user_data_dir = tmp_profile  # just to keep track

        # Using undetected_chromedriver for stealth:
        # driver_options = uc.ChromeOptions()
        driver_options = Options()
        page_load_strategy = str(
            browser_profile.get("page_load_strategy") or ""
        ).lower()
        if page_load_strategy in {"eager", "none"}:
            driver_options.page_load_strategy = page_load_strategy
        if headless:
            # For Chrome 109+, "headless=new" is recommended; fallback if it fails
            driver_options.add_argument("--headless=new")

        # Key ephemeral & performance log settings
        driver_options.add_argument(f"--user-data-dir={tmp_profile}")
        driver_options.add_argument("--no-sandbox")
        driver_options.add_argument("--disable-dev-shm-usage")
        if stealth:
            apply_stealth_options(driver_options)
        else:
            driver_options.add_argument("--window-size=1920,1080")
            driver_options.add_argument("--disable-blink-features=AutomationControlled")
            driver_options.add_argument("--enable-automation")
        for chrome_arg in _browser_profile_chrome_args(browser_profile, chrome_path):
            driver_options.add_argument(chrome_arg)
        driver_options.add_argument("--disable-infobars")
        driver_options.add_argument("--disable-background-networking")
        driver_options.add_argument("--disable-features=TranslateUI")
        driver_options.add_argument("--disable-background-timer-throttling")
        driver_options.add_argument("--disable-backgrounding-occluded-windows")
        driver_options.add_argument("--disable-breakpad")
        driver_options.add_argument(
            "--disable-component-extensions-with-background-pages"
        )  # Disables unnecessary extensions
        driver_options.add_argument(
            "--disable-client-side-phishing-detection"
        )  # Speeds up execution
        driver_options.add_argument(
            "--disable-default-apps"
        )  # Prevents default apps from loading
        driver_options.add_argument(
            "--disable-hang-monitor"
        )  # Prevents Chrome from freezing when unresponsive
        driver_options.add_argument(
            "--disable-ipc-flooding-protection"
        )  # Prevents IPC issues
        driver_options.add_argument(
            "--disable-renderer-backgrounding"
        )  # Ensures no CPU throttling
        if not stealth:
            driver_options.add_argument(
                "--enable-automation"
            )  # Explicitly marks as automation-friendly
        driver_options.add_argument(
            "--force-device-scale-factor=1"
        )  # Prevents UI scaling issues
        driver_options.add_argument(
            "--force-color-profile=srgb"
        )  # Prevents color space issues
        driver_options.add_argument(
            "--metrics-recording-only"
        )  # Reduces telemetry load
        driver_options.add_argument(
            "--safebrowsing-disable-auto-update"
        )  # Reduces network requests
        driver_options.add_argument("--disable-translate")  # Prevents translation UI
        driver_options.add_argument("--no-first-run")  # Skips first-time setup
        driver_options.add_argument(
            "--disable-notifications"
        )  # Disables notification popups
        driver_options.add_argument("--disable-extensions")  # Reduces memory footprint
        driver_options.add_argument("--disable-site-isolation-trials")

        # Performance logs → HAR-like data
        # driver_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        if proxy:
            driver_options.add_argument(f"--proxy-server={proxy}")

        version = get_chrome_version(chrome_path)

        try:
            driver = launch_headless_chrome(driver_options, version=version)
            if driver is None:
                _purge_driver_cache()
                driver = launch_headless_chrome(driver_options, version)
                if driver is None:
                    raise ValueError("missing driver!")
        except Exception:
            # Only a failure to start Chrome affects unrelated sources. Page
            # timeouts, rejected content and selector failures stay URL-local.
            _record_renderer_failure("headless", "startup_failed")
            raise
        _clear_renderer_failure("headless")

        # This kiosk dashboard needs a full content viewport, not Chrome's
        # smaller inner area from an outer window-size argument.
        if str(name or "").lower() == "eyebatsystemglimpse":
            driver.execute_cdp_cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1920,
                    "height": 1080,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )

        driver.set_page_load_timeout(timeout)
        _apply_browser_dark_preference(driver, dark, invert)

        # Navigate
        try:
            driver.get(url)
        except TimeoutException:
            if not browser_profile.get("continue_after_load_timeout"):
                raise
            logging.warning(
                "[%s] Page load timed out; continuing with rendered state: %s",
                name,
                clean_url,
            )
        # Chrome's own error UI cannot benefit from a rendering settle delay.
        # Keep the later checks for failures that appear while the page settles.
        if _reject_browser_error_page(driver, url, name):
            return False
        time.sleep(1.25 if is_sdm_webrtc_preview else 5)
        profile_delay = float(browser_profile.get("post_load_delay") or 0.0)
        if profile_delay > 0 and not is_sdm_webrtc_preview:
            time.sleep(profile_delay)
        if _reject_browser_error_page(driver, url, name):
            return False
        # Basic wait for DOM. Tweak as needed or switch to explicit waits.

        # Some full-screen browser apps put a first-run tutorial over useful
        # content. Prefer a precise profile-controlled click over broad DOM
        # removal so the app can update its own state and render normally.
        clicked_profile_controls = 0
        for click_xpath_candidate in browser_profile.get("click_xpaths") or ():
            clicked_profile_controls += _click_profile_control(
                driver, str(click_xpath_candidate), name
            )
        if clicked_profile_controls and not is_sdm_webrtc_preview:
            time.sleep(float(browser_profile.get("post_click_delay") or 1.0))

        # Remove popups
        popup_xpaths = []
        if popup_xpath:
            popup_xpaths.append(popup_xpath)
        popup_xpaths.extend(browser_profile.get("popup_xpaths") or ())
        for popup_xpath_candidate in popup_xpaths:
            try:
                removed = _remove_popup(driver, popup_xpath_candidate)
                if removed == 0:
                    logging.debug(
                        "[%s] popup_xpath matched no elements: %s",
                        name,
                        popup_xpath_candidate,
                    )
            except Exception as e:
                logging.debug(
                    "[%s] popup_xpath remove failed (%s): %s",
                    name,
                    popup_xpath_candidate,
                    e,
                )
        # Best-effort removal of large fixed/sticky overlays (cookie banners, modals).
        removed_overlays = _strip_fixed_overlays(driver, name)
        if removed_overlays:
            logging.debug(
                "[%s] stripped %d fixed/sticky overlays", name, removed_overlays
            )
        removed_site_chrome = _apply_browser_site_dom_cleanup(
            driver,
            tuple(browser_profile.get("hide_selectors") or ()),
            name,
        )
        if removed_site_chrome:
            logging.debug("[%s] hid %d site chrome elements", name, removed_site_chrome)
        if browser_profile.get("hubitat_cloud_dashboard"):
            hubitat_cleanup = _apply_hubitat_cloud_dashboard_visual_cleanup(
                driver, name
            )
            logging.debug(
                "[%s] Hubitat visual cleanup images=%d statuses=%d hidden=%d",
                name,
                hubitat_cleanup["images"],
                hubitat_cleanup["statuses"],
                hubitat_cleanup["hidden"],
            )
            if hubitat_cleanup["images"] or hubitat_cleanup["statuses"]:
                time.sleep(
                    float(browser_profile.get("hubitat_cleanup_settle_delay") or 0.75)
                )
            hubitat_error_reason = _hubitat_cloud_dashboard_error_reason(
                driver, clean_url, name
            )
            if hubitat_error_reason:
                logging.warning(
                    "[%s] Rejecting Hubitat dashboard capture: %s",
                    name,
                    hubitat_error_reason,
                )
                record_preflight_backoff(
                    url,
                    hubitat_error_reason,
                    PREFLIGHT_BACKOFF_BROWSER_FAIL,
                )
                return False
        if dark and browser_profile.get("force_dark_visual_filter"):
            if _apply_force_dark_visual_filter(
                driver,
                name,
                bool(browser_profile.get("preserve_visual_media_on_dark_filter")),
                str(browser_profile.get("dark_visual_filter_mode") or "invert"),
            ):
                time.sleep(float(browser_profile.get("post_dark_filter_delay") or 0.5))

        if dark and not invert:
            _apply_map_dark_background(driver, clean_url, name)

        # If dedicated_selector is set, capture that region instead of full page
        active_dedicated_selector = dedicated_selector or str(
            browser_profile.get("auto_dedicated_xpath") or ""
        )
        if active_dedicated_selector:
            try:
                # Some pages (especially heavy JS sites) need a bit of time before
                # the target element is present *and* laid out at its final size.
                element = None
                is_sdm_webrtc_preview_url = (
                    "/integrations/google/webrtc/preview" in str(url or "")
                )
                wait_budget = 25 if is_sdm_webrtc_preview_url else 12
                deadline = time.time() + min(wait_budget, max(0, timeout - 1))
                last_exc = None
                while time.time() < deadline:
                    try:
                        cand = driver.find_element(By.XPATH, active_dedicated_selector)
                        if is_sdm_webrtc_preview_url:
                            preview_state = {}
                            try:
                                preview_state = (
                                    driver.execute_script(
                                        "return {"
                                        "state: document.body.dataset ? (document.body.dataset.sdmState || '') : '',"
                                        "ready: document.body.dataset ? (document.body.dataset.sdmReady || '') : '',"
                                        "error: document.body.dataset ? (document.body.dataset.sdmError || '') : '',"
                                        "status: (document.getElementById('status') || {}).textContent || ''"
                                        "};"
                                    )
                                    or {}
                                )
                            except Exception:
                                preview_state = {}
                            preview_error = str(
                                preview_state.get("error") or ""
                            ).strip()
                            preview_ready = str(
                                preview_state.get("ready") or ""
                            ).strip()
                            preview_state_name = str(
                                preview_state.get("state") or ""
                            ).strip()
                            preview_status = str(
                                preview_state.get("status") or ""
                            ).strip()
                            if preview_error:
                                raise TimeoutException(
                                    "SDM preview error: "
                                    f"{preview_error} (status={preview_status})"
                                )
                            if preview_ready != "1":
                                logging.debug(
                                    "[%s] waiting on SDM preview state=%s status=%s",
                                    name,
                                    preview_state_name or "unknown",
                                    preview_status or "",
                                )
                                time.sleep(0.75)
                                continue
                        tag = (
                            driver.execute_script(
                                "return arguments[0].tagName.toLowerCase();", cand
                            )
                            or ""
                        )
                        rect = getattr(cand, "rect", None) or {}
                        w = float(rect.get("width") or 0)
                        h = float(rect.get("height") or 0)
                        if tag == "img":
                            # Wait for images to actually load; otherwise screenshots
                            # can be a single-color placeholder that triggers blank detection.
                            try:
                                loaded_meta = driver.execute_script(
                                    "return {"
                                    "complete: !!arguments[0].complete,"
                                    "nw: arguments[0].naturalWidth || 0,"
                                    "ready: arguments[0].dataset ? arguments[0].dataset.ready : ''"
                                    "};",
                                    cand,
                                )
                                loaded = bool(
                                    loaded_meta.get("complete")
                                    and int(loaded_meta.get("nw") or 0) > 100
                                )
                                if (
                                    loaded
                                    and is_sdm_webrtc_preview_url
                                    and str(loaded_meta.get("ready") or "") != "1"
                                ):
                                    loaded = False
                            except Exception:
                                loaded = True
                            if not loaded:
                                time.sleep(0.75)
                                continue
                            # WeatherBug camera stills can start small and then expand;
                            # wait briefly for a more useful layout.
                            if w < 650 or h < 350:
                                time.sleep(0.75)
                                continue
                        if tag == "video":
                            try:
                                vstate = driver.execute_script(
                                    "return {"
                                    "rs: arguments[0].readyState || 0,"
                                    "vw: arguments[0].videoWidth || 0,"
                                    "vh: arguments[0].videoHeight || 0,"
                                    "ct: arguments[0].currentTime || 0"
                                    "};",
                                    cand,
                                )
                            except Exception:
                                vstate = {"rs": 0, "vw": 0, "vh": 0, "ct": 0}
                            if (
                                int(vstate.get("rs") or 0) < 2
                                or int(vstate.get("vw") or 0) < 100
                                or int(vstate.get("vh") or 0) < 100
                                or float(vstate.get("ct") or 0.0) < 0.10
                            ):
                                time.sleep(0.6)
                                continue
                        element = cand
                        break
                    except Exception as exc:
                        last_exc = exc
                        time.sleep(0.5)
                if element is None:
                    if last_exc is not None:
                        raise last_exc
                    raise TimeoutException(
                        "Dedicated selector not ready before timeout: "
                        f"{active_dedicated_selector}"
                    )
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)
                # Hubitat can replace its tile DOM after the initial cleanup.
                # Reapply at the capture boundary, after selector/readiness waits.
                if browser_profile.get("hubitat_cloud_dashboard"):
                    _settle_hubitat_dashboard_for_capture(driver, name)
                element.screenshot(partial_screenshot)

                # Guard against bad XPath crops that produce tiny/blank captures.
                if os.path.exists(partial_screenshot):
                    try:
                        viewport_w = int(
                            driver.execute_script(
                                "return Math.max(document.documentElement.clientWidth||0, window.innerWidth||0);"
                            )
                            or 0
                        )
                        viewport_h = int(
                            driver.execute_script(
                                "return Math.max(document.documentElement.clientHeight||0, window.innerHeight||0);"
                            )
                            or 0
                        )
                        with Image.open(partial_screenshot) as _im:
                            shot_w, shot_h = _im.size
                        shot_area = max(1, shot_w * shot_h)
                        viewport_area = max(1, viewport_w * viewport_h)
                        shot_ratio = shot_area / viewport_area
                        shot_kb = os.path.getsize(partial_screenshot) / 1024.0
                        element_tag = ""
                        element_src = ""
                        try:
                            element_tag = (
                                driver.execute_script(
                                    "return arguments[0].tagName.toLowerCase();",
                                    element,
                                )
                                or ""
                            )
                            element_src = (element.get_attribute("src") or "").strip()
                        except Exception:
                            element_tag = ""
                            element_src = ""

                        is_weatherbug_cam = element_tag == "img" and url_matches_host(
                            element_src, "cameras-cam.cdn.weatherbug.net"
                        )
                        is_video_crop = element_tag == "video"
                        # Guard against bad XPath crops that produce tiny/blank captures.
                        # For WeatherBug camera still images, the element can be a
                        # relatively small portion of the viewport, so don't use
                        # the viewport-area ratio heuristic.
                        if is_video_crop:
                            # Video frames can compress to small files at night
                            # while still being valid captures.
                            is_tiny_crop = shot_w < 700 or shot_h < 350
                        elif is_weatherbug_cam:
                            is_tiny_crop = shot_w < 450 or shot_h < 250 or shot_kb < 12
                        else:
                            is_tiny_crop = (
                                shot_w < 700
                                or shot_h < 350
                                or shot_kb < 12
                                or shot_ratio < 0.12
                            )
                        if is_tiny_crop:
                            logging.warning(
                                "[%s] dedicated_xpath tiny crop; falling back to full-page. xpath=%s shot=%sx%s %.1fKB viewport=%sx%s ratio=%.3f",
                                name,
                                active_dedicated_selector,
                                shot_w,
                                shot_h,
                                shot_kb,
                                viewport_w,
                                viewport_h,
                                shot_ratio,
                            )
                            os.remove(partial_screenshot)
                    except Exception as e:
                        logging.debug(
                            "[%s] dedicated_xpath crop validation failed: %s", name, e
                        )
            except Exception as e:
                logging.warning(
                    "[%s] dedicated_xpath failed; falling back to full-page. xpath=%s err=%s",
                    name,
                    active_dedicated_selector,
                    e,
                )

        # Fallback to entire page if partial didn't get created
        if not os.path.exists(partial_screenshot):
            if is_sdm_webrtc_preview:
                # An unready preview is a status/error page, never a camera
                # frame. Keep the last accepted image instead of falling back.
                record_preflight_backoff(url, "sdm_preview_not_ready", 45)
                return False
            if browser_profile.get("hubitat_cloud_dashboard"):
                _settle_hubitat_dashboard_for_capture(driver, name)
            driver.save_screenshot(partial_screenshot)

        # Attempt to gather performance logs → HAR
        # if har_output_path:
        #    _save_har_logs(driver, har_output_path)

        # Post-process final
        if _reject_browser_error_page(driver, url, name):
            if os.path.exists(partial_screenshot):
                os.remove(partial_screenshot)
            return False
        success = _finalize_screenshot(
            partial_screenshot,
            output_path,
            name,
            invert,
            dark,
            stabilize_mode=stabilize_mode,
            url=url,
            clean_url=clean_url,
            allow_sparse_capture=allow_sparse_capture,
        )
        if success and not os.path.exists(output_path):
            Path(output_path).touch()

    except TimeoutException:
        logging.warning(f"[capture_screenshot_and_har] Timeout error for {clean_url}")
    except WebDriverException:
        logging.warning(f"[capture_screenshot_and_har] WebDriver error for {clean_url}")
    except Exception as e:
        logging.error(f"[capture_screenshot_and_har] Unexpected error: {clean_url} {e}")
        logging.warning("capture failed on CI: %s", e)
        success = False
    finally:
        # Gracefully close the driver
        if driver:
            try:
                driver.quit()
            except Exception as ex:
                logging.warning("driver.quit() failed: %s", ex)
            # Force-kill child processes if needed
            kill_driver_process(driver)

        # Remove ephemeral user-data-dir
        if user_data_dir and os.path.exists(user_data_dir):
            try:
                shutil.rmtree(user_data_dir, ignore_errors=True)
            except Exception as e:
                logging.debug(f"Could not remove ephemeral dir {user_data_dir}: {e}")

        if user_data_dir and os.path.exists(user_data_dir):
            logging.warning("data dir did not clean, %s", user_data_dir)

        _release_browser_capture_file_lock(browser_lock_file, name)

    return success


######################
# Helper subroutines #
######################


def _finalize_screenshot(
    tmp_path,
    final_path,
    name,
    invert,
    dark,
    *,
    stabilize_mode: str = "off",
    url: str | None = None,
    clean_url: str | None = None,
    allow_sparse_capture: bool = False,
):
    """
    Checks if tmp_path exists, does some post-processing, and renames to final_path.
    Returns True on success, False otherwise.
    """
    tmp_path = _sanitize_path(tmp_path)
    final_path = _sanitize_path(final_path)

    if not os.path.exists(tmp_path):
        return False

    def _safe_move(src: str, dst: str) -> None:
        """Move a file even when src/dst live on different filesystems."""

        try:
            os.replace(src, dst)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            # Cross-device move (e.g., /tmp -> /data). shutil.move falls back to
            # copy+unlink.
            shutil.move(src, dst)

    try:
        with Image.open(tmp_path) as img:
            img = img.convert("RGB")
            is_sdm_webrtc_preview = bool(
                url and "/integrations/google/webrtc/preview" in str(url)
            )
            is_hubitat_dashboard_capture = _is_hubitat_cloud_dashboard_url(url) or str(
                name
            ).lower().startswith("hubitat")

            reject_reason = _captured_frame_rejection_reason(img)
            if (
                reject_reason in {"blank", "loading"}
                and allow_sparse_capture
                and is_sparse_dashboard_frame(img)
            ):
                logging.info(
                    "[%s] Accepting sparse trusted dashboard frame: %s",
                    name,
                    clean_url or sanitize_url(url or ""),
                )
                reject_reason = None
            if reject_reason == "blank" and is_sdm_webrtc_preview:
                # SDM WebRTC feeds can be legitimately low-light at night; keep the
                # frame rather than replacing it with "No screenshot available".
                gray = np.asarray(img.convert("L"))
                h, w = gray.shape[:2]
                c = gray[
                    int(h * 0.15) : int(h * 0.8),
                    int(w * 0.1) : int(w * 0.9),
                ]
                center_mean = float(c.mean()) if c.size else 0.0
                center_std = float(c.std()) if c.size else 0.0
                if center_std > 2.5 or center_mean > 8.0:
                    logging.info(
                        (
                            "[%s] Accepting low-light SDM WebRTC frame "
                            "(center_mean=%.2f center_std=%.2f)"
                        ),
                        name,
                        center_mean,
                        center_std,
                    )
                    reject_reason = None
            if reject_reason is not None:
                logging.warning(
                    "[%s] The captured screenshot was rejected due to %s content.",
                    name,
                    reject_reason,
                )
                if url:
                    record_preflight_backoff(
                        url,
                        (
                            "blank_capture"
                            if reject_reason == "blank"
                            else f"{reject_reason}_capture"
                        ),
                        PREFLIGHT_BACKOFF_BROWSER_FAIL,
                    )
                orig_path = final_path + ".orig.png"
                _safe_move(tmp_path, orig_path)
                if os.path.exists(final_path) and _is_valid_png(final_path):
                    return CAPTURE_STALE_PREVIOUS
                create_placeholder(tmp_path, name)
                success = False
            else:
                # Optional background removal
                img = _postprocess_still_image(
                    img,
                    final_path,
                    name,
                    dark=dark,
                    stabilize_mode=stabilize_mode,
                    remove_bg=(
                        not is_sdm_webrtc_preview and not is_hubitat_dashboard_capture
                    ),
                )

                # If you want to do naive “darkening” or inverting more thoroughly,
                # you can do that here. For example:
                # if dark:
                #    img = apply_dark_mode(img)

                # Save back
                img.save(tmp_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)
                success = True

        # Now add a timestamp overlay. If this fails the file may be removed.
        add_timestamp(
            tmp_path,
            name=name,
            invert=invert,
            show_name=not is_hubitat_dashboard_capture,
        )

        # If the timestamp step removed the screenshot, replace it with a
        # placeholder image rather than failing outright.
        if not os.path.exists(tmp_path):
            logging.warning("Timestamp overlay failed; creating placeholder instead")
            create_placeholder(tmp_path, name)

        # Finally rename after verifying the file exists.
        if not os.path.exists(tmp_path):
            return False

        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        _safe_move(tmp_path, final_path)

        logging.debug(f"SAVED screenshot -> {final_path}")
        return success

    except Exception as e:
        logging.error(f"Screenshot finalization error: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _capture_danger_mode(
    url,
    partial_screenshot,
    popup_xpath,
    dedicated_selector,
    timeout,
    name,
    invert,
    dark,
) -> bool:
    """
    Attach to an existing local Chrome with remote-debugging-port configured by
    ``DANGER_PORT``,
    open a new tab, capture a screenshot, close the tab, and yield the result.

    Because we are hooking into a real user’s Chrome, you must be aware that
    you can break them if you do something invasive. Also, Chrome or the user
    might close the new tab any time.

    Return True if partial_screenshot was created, else False.
    """
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By

    # This part uses normal Selenium for the attach:
    danger_options = webdriver.ChromeOptions()
    danger_options.debugger_address = f"127.0.0.1:{config.DANGER_PORT}"

    driver = None
    original_window = None
    new_tab_handle = None

    clean_url = sanitize_url(url)
    try:
        driver = webdriver.Chrome(options=danger_options)
        driver.set_page_load_timeout(timeout)

        # Record the existing window we were in
        original_window = driver.current_window_handle

        # Open a new blank tab, then navigate
        driver.execute_script("window.open('about:blank','_blank');")
        time.sleep(0.5)
        all_tabs = driver.window_handles
        new_tab_handle = all_tabs[-1]  # the newly opened blank
        driver.switch_to.window(new_tab_handle)
        _apply_browser_dark_preference(driver, dark, invert)
        logging.debug("trying %s", clean_url)
        driver.get(url)
        logging.debug("success, screenshotting %s", clean_url)
        _send_input_event()
        time.sleep(3)

        time.sleep(5)

        # Remove popups
        if _reject_browser_error_page(driver, url, name):
            return False
        if popup_xpath:
            _remove_popup(driver, popup_xpath)

        # Dedicated selector
        if dedicated_selector:
            try:
                el = driver.find_element(By.XPATH, dedicated_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", el)
                time.sleep(5)
                el.screenshot(partial_screenshot)
            except Exception as e:
                logging.warning(f"[danger_mode] dedicated_selector error: {e}")

        # Fallback entire page
        if not os.path.exists(partial_screenshot):
            driver.save_screenshot(partial_screenshot)

        if _reject_browser_error_page(driver, url, name):
            if os.path.exists(partial_screenshot):
                os.remove(partial_screenshot)
            return False
        return os.path.exists(partial_screenshot)

    except TimeoutException:
        # print("timeout1")
        logging.warning(f"[danger_mode] Timeout while loading page: {clean_url}")
        return False
    except Exception as e:
        logging.error("[danger_mode] Unexpected error: %s", e)
        return False
    finally:
        # Close just our new tab
        try:
            if new_tab_handle:
                driver.switch_to.window(new_tab_handle)
                driver.close()
        except Exception as ex:
            logging.debug(f"Could not close new tab in danger mode: {ex}")

        # Switch back to the original window
        if original_window:
            try:
                driver.switch_to.window(original_window)
            except Exception as ex:
                logging.debug(
                    f"Could not switch to original window in danger mode: {ex}"
                )

        # Always shut down the Chrome driver to avoid FD leaks
        if driver:
            try:
                driver.quit()
            except Exception as ex:
                logging.debug(f"driver.quit() failed in danger mode: {ex}")


def _strip_fixed_overlays(driver, name: str) -> int:
    """Best-effort removal of large fixed/sticky overlays (cookie banners, modals).

    This is intentionally conservative: it only hides elements that are
    position:fixed/sticky, are visible, and occupy a meaningful fraction of
    the viewport but not *most* of it. When in doubt, it leaves the DOM
    untouched.
    """

    try:
        removed = driver.execute_script("""
            const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
            const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
            const varea = Math.max(1, vw * vh);
            const overlayTokens = [
              'modal', 'popup', 'popover', 'dialog', 'overlay', 'drawer',
              'cookie', 'consent', 'gdpr', 'privacy', 'newsletter',
              'subscribe', 'email-signup', 'email-capture', 'signup',
              'headlessui', 'onetrust', 'attentive', 'ltkpopup', 'privy',
              'klaviyo', 'justuno', 'wisepops', 'flyout', 'dropdown',
              'tooltip', 'login', 'sign-in', 'signin', 'account',
              'best-experience', 'rewards'
            ];
            const sceneTokens = [
              'map', 'canvas', 'video', 'player', 'camera', 'webcam',
              'main-content', 'product-grid', 'hero', 'chart', 'graph'
            ];
            let removed = 0;

            const candidates = Array.from(document.querySelectorAll('body *'));
            for (const el of candidates) {
              try {
                const style = window.getComputedStyle(el);
                if (!style) continue;
                const pos = style.position;
                if (pos !== 'fixed' && pos !== 'sticky') continue;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

                const r = el.getBoundingClientRect();
                if (!r || r.width <= 0 || r.height <= 0) continue;
                // Skip if fully offscreen
                if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;

                const area = r.width * r.height;
                const frac = area / varea;
                const tag = String(el.tagName || '').toLowerCase();
                const identity = [
                  el.id || '',
                  typeof el.className === 'string' ? el.className : '',
                  el.getAttribute('role') || '',
                  el.getAttribute('aria-modal') || '',
                  el.getAttribute('data-testid') || '',
                  el.getAttribute('aria-label') || '',
                  el.getAttribute('title') || ''
                ].join(' ').toLowerCase();
                const hasOverlayHint = overlayTokens.some((token) => identity.includes(token));
                const hasSceneHint = sceneTokens.some((token) => identity.includes(token));
                const isModal = el.getAttribute('aria-modal') === 'true' || el.getAttribute('role') === 'dialog';
                const isSceneTag = ['body', 'html', 'main', 'canvas', 'video', 'img'].includes(tag);

                // Too small to matter
                if (frac < 0.05) continue;
                // Likely the main content (or full-screen app)
                if (frac > 0.80) continue;
                if (!hasOverlayHint && !isModal) {
                  if (isSceneTag && frac > 0.05) continue;
                  if (hasSceneHint && frac > 0.12) continue;
                }

                // Heuristic: overlays often sit at the top/bottom/center.
                const nearEdge = (r.top < vh * 0.15) || (r.bottom > vh * 0.85);
                if (!nearEdge && frac < 0.20) continue;

                el.style.setProperty('display', 'none', 'important');
                removed++;
              } catch (e) {
                // ignore per-node failures
              }
            }
            return removed;
            """)
        return int(removed or 0)
    except Exception as exc:
        logging.debug("[%s] overlay strip failed: %s", name, exc)
        return 0


def _remove_popup(driver, popup_xpath):
    """
    If there's an annoying overlay or popup, remove it from the DOM by XPATH.
    Returns the number of removed elements.
    """
    removed = 0
    try:
        elements = driver.find_elements(By.XPATH, popup_xpath)
        for el in elements:
            did_remove = driver.execute_script(
                """
                let el = arguments[0];
                const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0, 1);
                const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0, 1);
                const varea = Math.max(1, vw * vh);
                const popupTextTokens = [
                  'log in for the best experience',
                  'track your orders',
                  'save items for later',
                  'view your order history',
                  'create an account'
                ];
                const matchedText = String(el.innerText || el.textContent || '').toLowerCase();
                if (popupTextTokens.some((token) => matchedText.includes(token))) {
                  let candidate = el;
                  for (let node = el; node && node !== document.body; node = node.parentElement) {
                    const nodeRect = node.getBoundingClientRect();
                    if (!nodeRect || nodeRect.width <= 0 || nodeRect.height <= 0) continue;
                    const nodeFrac = (nodeRect.width * nodeRect.height) / varea;
                    const nodeText = String(node.innerText || node.textContent || '').toLowerCase();
                    if (
                      nodeFrac > 0.003 &&
                      nodeFrac < 0.35 &&
                      popupTextTokens.some((token) => nodeText.includes(token))
                    ) {
                      candidate = node;
                    }
                  }
                  el = candidate;
                }
                const tag = String(el.tagName || '').toLowerCase();
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                const frac = (rect.width * rect.height) / varea;
                const text = [
                  el.id || '',
                  typeof el.className === 'string' ? el.className : '',
                  el.getAttribute('role') || '',
                  el.getAttribute('aria-modal') || '',
                  el.getAttribute('data-testid') || '',
                  el.getAttribute('aria-label') || '',
                  el.getAttribute('title') || '',
                  String(el.innerText || el.textContent || '').slice(0, 300)
                ].join(' ').toLowerCase();
                const overlayTokens = [
                  'modal', 'popup', 'popover', 'dialog', 'overlay', 'drawer',
                  'cookie', 'consent', 'gdpr', 'privacy', 'newsletter',
                  'subscribe', 'email-signup', 'email-capture', 'signup',
                  'headlessui', 'onetrust', 'attentive', 'ltkpopup', 'privy',
                  'klaviyo', 'justuno', 'wisepops', 'flyout', 'dropdown',
                  'tooltip', 'login', 'sign-in', 'signin', 'account',
                  'best experience', 'rewards'
                ];
                const sceneTokens = [
                  'map', 'canvas', 'video', 'player', 'camera', 'webcam',
                  'main-content', 'product-grid', 'hero', 'chart', 'graph'
                ];
                const hasOverlayHint = overlayTokens.some((token) => text.includes(token));
                const hasSceneHint = sceneTokens.some((token) => text.includes(token));
                const isModal = el.getAttribute('aria-modal') === 'true' || el.getAttribute('role') === 'dialog';
                const isFloating = style.position === 'fixed' || style.position === 'sticky';
                const isSceneTag = ['body', 'html', 'main', 'canvas', 'video', 'img'].includes(tag);

                // XPath fields are operator-entered and sometimes broad. Never
                // remove a scene-sized map/video/main element unless it has a
                // strong overlay identity.
                if (!hasOverlayHint && !isModal) {
                  if (isSceneTag && frac > 0.15) return false;
                  if (hasSceneHint && frac > 0.25) return false;
                  if (frac > 0.55) return false;
                }

                // Full-screen Cloudflare / interstitial pages are content, not
                // removable chrome. Hiding them only creates a blank capture.
                if (
                  frac > 0.82 &&
                  /cloudflare|checking your browser|verify you are human/.test(
                    String(document.body && document.body.innerText || '').toLowerCase()
                  )
                ) {
                  return false;
                }

                if (!hasOverlayHint && !isModal && !isFloating && frac > 0.35) {
                  return false;
                }

                el.remove();
                return true;
                """,
                el,
            )
            if did_remove:
                removed += 1
    except Exception as e:
        logging.debug(f"_remove_popup error: {e}")
    return removed


def _click_profile_control(driver, click_xpath: str, name: str) -> int:
    """Click a site-profile control such as a known first-run dismiss button."""

    if not click_xpath:
        return 0
    clicked = 0
    try:
        elements = driver.find_elements(By.XPATH, click_xpath)
        for el in elements:
            did_click = driver.execute_script(
                """
                const el = arguments[0];
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (!style || !rect || rect.width <= 0 || rect.height <= 0) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                el.click();
                return true;
                """,
                el,
            )
            if did_click:
                clicked += 1
                break
    except Exception as exc:
        logging.debug("[%s] profile click failed (%s): %s", name, click_xpath, exc)
    return clicked


def _save_har_logs(driver, har_output_path):
    """
    Grab performance logs from Chrome and write them to a file (JSON).
    This is not a perfect HAR, but it’s close enough for many cases.
    """
    try:
        logs = driver.get_log("performance")
        # logs is a list of dict with keys: { "level": str, "message": str, "timestamp": int }

        with open(har_output_path, "w", encoding="utf-8") as f:
            for entry in logs:
                f.write(entry["message"] + "\n")
        logging.debug(f"Saved HAR-like logs -> {har_output_path}")

    except Exception as e:
        logging.error(f"Could not fetch performance logs: {e}")


def create_blank_frame(name: str, size=(1280, 720)) -> str:
    """Generate a blank screenshot for ``name``.

    A timestamp and camera name are added so the resulting image can be
    spliced into video sequences when templates change.

    Parameters
    ----------
    name : str
        Template identifier used to determine the storage path.

    size : tuple, optional
        Image width and height. Defaults to ``(1280, 720)``.

    Returns
    -------
    str
        Absolute path to the created image.
    """

    output_dir = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name))
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    image_path = os.path.join(output_dir, f"{name}_{timestamp}_blank.png")

    image = Image.new("RGB", size, (0, 0, 0))
    image.save(image_path, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)
    add_timestamp(image_path, name=name)

    return image_path
