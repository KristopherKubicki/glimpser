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
import hashlib
import io
import ipaddress
import json
import logging
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
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import numpy as np
import psutil
import requests
import urllib3
import yt_dlp as youtube_dl
from dateutil import tz
from pdf2image import convert_from_bytes
from PIL import Image, ImageDraw, ImageFile, ImageFont, ImageOps
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from werkzeug.utils import secure_filename

from app import config
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
from app.utils.logging_utils import sanitize_url
from app.utils.validators import validate_proxy, validate_url

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
STREAM_PROBE_TIMEOUT = 5
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
    if scheme == "rtsp":
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
        "stream=codec_name",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        "-analyzeduration",
        analyze_duration,
        "-probesize",
        probe_size,
    ]
    if scheme == "rtsp":
        base_cmd.extend(["-stimeout", str(int(timeout * 1_000_000))])

    transports = [None]
    if scheme == "rtsp":
        transports = _rtsp_transport_candidates(url)
    per_attempt_timeout = max(2, int(timeout / max(len(transports), 1)))
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
            if streams:
                stream = streams[0]
                fingerprint = {
                    "codec": stream.get("codec_name"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "fps": stream.get("r_frame_rate"),
                    "pix_fmt": stream.get("pix_fmt"),
                    "bit_rate": stream.get("bit_rate"),
                }
                _set_stream_fingerprint(url, fingerprint)
        except Exception:
            logging.debug("ffprobe fingerprint parse failed for %s", sanitize_url(url))
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
    if scheme == "rtsp":
        analyze_duration = ANALYZE_DURATION_RTSP
        probe_size = PROBE_SIZE_RTSP
    elif _is_hdhomerun_like_stream_url(url):
        analyze_duration = ANALYZE_DURATION_OTHER
        probe_size = PROBE_SIZE_OTHER
    elif scheme not in {"http", "https"}:
        analyze_duration = ANALYZE_DURATION_OTHER
        probe_size = PROBE_SIZE_OTHER

    base_cmd = [FFMPEG_PATH, "-hide_banner", "-v", "error", "-xerror"]
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
    if scheme == "rtsp":
        transports = _rtsp_transport_candidates(url)

    probe_timeout = max(2, min(timeout, 8))
    per_attempt_timeout = max(2, int(probe_timeout / max(len(transports), 1)))
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
        elif scheme == "rtsp" and transport:
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
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.lower()
    return url.lower()


def _domain_key(url: str) -> str | None:
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
    return url.lower()


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
    if entry.get("lock_until", 0) > time.time():
        return False
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
        if not is_system_online():
            cached_driver = _find_cached_chromedriver()
            if not cached_driver:
                logging.warning("System offline; skipping driver setup")
                return None
            try:
                service = Service(cached_driver)
                driver = webdriver.Chrome(service=service, options=opts)
                _driver_local.driver = driver
                return driver
            except Exception as exc:
                logging.error("Failed to launch cached driver: %s", exc)
                return None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            _driver_local.driver = driver
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
    """Crop the image to remove the background color border and ensure a 16:9 aspect ratio."""
    if background_color is None:
        background_color = detect_background_color(image)
    # Find the bounding box of the non-background area
    bbox = find_bounding_box(image, background_color, threshold)

    # Adjust the bounding box to fit a 16:9 aspect ratio
    if bbox:
        bbox = adjust_bbox_to_aspect_ratio(bbox, image.size, aspect_ratio=(16, 9))
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
        return True

    gray = np.dot(arr, [0.2126, 0.7152, 0.0722])
    gray_uint = np.clip(gray, 0, 255).astype(np.uint8)
    luma = float(gray.mean())
    gray_std = float(gray.std())

    # ---------- 3.  “Edge density?”  ----------
    # Low edge density + low variance/entropy is a strong blank signal.
    edge_v = np.abs(np.diff(gray, axis=0)) > 12
    edge_h = np.abs(np.diff(gray, axis=1)) > 12
    edge_density = (edge_v.mean() + edge_h.mean()) / 2.0

    # ---------- 2.  “Flat image?”  ----------
    # Low global std-dev ≈ little structure / shapes
    if gray_std < text_std_threshold and edge_density < edge_threshold:
        return True

    # ---------- 3.  “Too dark?”  ----------
    # Use perceptual luma so pure-dark blue isn’t mis-treated
    if luma < dark_threshold and edge_density < edge_threshold:
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


def add_timestamp(image_path, name="unknown", invert=False):
    """Overlay name and timestamp onto an image.

    Args:
        image_path (str): Path to the PNG file.
        name (str): Label to render on the image.
        invert (bool): Invert text for dark images.
    """

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

            # Define the timestamp format

            zone = tz.gettz(TZ) or tz.UTC  # fall back if the name is invalid
            local_time = datetime.datetime.now(zone)
            tz_name = local_time.tzname() or ""
            timestamp = local_time.strftime("%Y-%m-%d %H:%M:%S")
            if tz_name:
                timestamp = f"{timestamp} {tz_name}"

            utc_time = datetime.datetime.utcnow()
            utc_timestamp = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")

            max_height = min(image.height, image.width * 9 // 16)
            font_size = int(max_height * 0.05)
            if font_size < 5:  # ignore tiny images
                return

            top_offset = (image.height - max_height) / 2

            # Use the helper to load fonts. The small font is half-sized.
            font = load_font(font_size)
            font_small = load_font(int(max(5, font_size / 2)))

            padding = 6

            # Render the name in the upper-left corner
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

            if utc_timestamp != timestamp:
                tz_bbox = draw.textbbox(
                    (0, 0), utc_timestamp + "Z", font=font_small, stroke_width=1
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
                    utc_timestamp + "Z",
                    font=font_small,
                    fill=(255, 255, 255, 255),
                    stroke_width=1,
                    stroke_fill=(0, 0, 0, 255),
                )

            # Save the image
            image.save(image_path, "PNG")

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
    img.save(image_path, "PNG")


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
    """

    proxy = validate_proxy(proxy)
    clean_url = sanitize_url(url)
    output_path = _sanitize_path(output_path)

    # ideally the timeout should be pretty high, its an image, and it could be real big
    timeout = max(timeout, 10)

    response = None

    cached = get_cached_status_code(url)
    if cached is not None and cached != 200:
        logging.debug(f"Skipping {clean_url} due to cached status {cached}")
        return False
    try:
        lua = UA
        if stealth:
            lua = random_user_agent()
        headers = {"user-agent": lua}
        proxies = {"http": proxy, "https": proxy} if proxy else None

        auth = get_preferred_auth(url, username, password)

        request_kwargs = dict(
            stream=True,
            timeout=(timeout, timeout * 3),
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
                timeout=(timeout, timeout * 3),
                verify=config.REQUEST_VERIFY_SSL,
                headers=headers,
                auth=auth,
            )
            if proxies:
                request_kwargs["proxies"] = proxies

            response = http_session().get(url, **request_kwargs)

        status = response.status_code
        if status == 429:
            record_rate_limit(url, response)
            return False
        set_cached_status_code(url, status)

        if status == 200:
            if response.content and len(response.content) <= IMAGE_HASH_MAX_BYTES:
                digest = hashlib.sha256(response.content).hexdigest()
                if digest == _get_image_hash(url):
                    response.close()
                    return True
                _set_image_hash(url, digest)
            # Open the image directly from the response bytes
            image = Image.open(io.BytesIO(response.content))
            response.close()

            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            image = image.convert("RGB")
            image = remove_background(image)
            if dark:
                apply_dark_mode(image)

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            tmp_path = output_path + ".tmp"

            # Save to a temporary file first so readers don't see partial data
            image.save(tmp_path, "PNG")
            if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
                add_timestamp(tmp_path, name=name, invert=invert)
                os.replace(tmp_path, output_path)
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
                response.close()
                return False
            auth = (
                get_digest_auth(url, username, password) if scheme == "digest" else auth
            )
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
            response.close()
            return False
        set_cached_status_code(url, response.status_code)

        if response.status_code != 200:
            logging.warning(f"Error downloading PDF: HTTP {response.status_code}")
            if response.status_code in {403, 404, 410}:
                _set_http_error(url, response.status_code)
            cas_error(url)
            return False

        # Convert the first page to an image directly from the response bytes
        pages = convert_from_bytes(response.content, first_page=1, last_page=1)
        if not pages:
            logging.error("Error converting PDF to image: No pages found")
            return False

        image = pages[0].convert("RGB")
        image = remove_background(image)
        if dark:
            image = apply_dark_mode(image)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tmp_path = output_path + ".tmp"
        image.save(tmp_path, "PNG")

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

    timeout = max(timeout, 3)

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

    # ARP can be useful for diagnosing LAN hosts, but requiring an existing ARP
    # entry is too strict. The first TCP connect attempt will populate ARP (for
    # on-link hosts), and routed subnets won't have a per-host ARP entry anyway.
    arp_missing = False
    if is_private_ip(ip_address):
        try:
            arp_entry = get_arp_output(ip_address, timeout)
            if b"no entry" in (arp_entry or b"").lower():
                arp_missing = True
        except Exception as e:
            logging.warning("failure to arp %s", e)

    try:

        def _attempt_connect(src_ip: str | None) -> int:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(timeout)
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
        if result != 0 and is_private_ip(ip_address):
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
        if arp_missing:
            logging.debug(
                "No ARP entry for %s before TCP connect_ex=%s", ip_address, result
            )
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


def _capture_or_download_inner(
    name: str,
    template: dict,
    url: str,
    clean_url: str,
    username: str | None,
    password: str | None,
) -> bool:
    # WeatherBug normalizes `/weather-camera/?cam=...` -> `/weather-camera?cam=...`.
    # Keep a stable URL to avoid redirect loops and make caching sane.
    if re.findall(
        r"^https?://(www\.)?weatherbug\.com/weather-camera/\?cam=", url, re.I
    ):
        url = url.replace("/weather-camera/?", "/weather-camera?", 1)
        clean_url = sanitize_url(url)

    popup_xpath = template.get("popup_xpath")
    dedicated_selector = template.get("dedicated_xpath")
    timeout = int(template.get("timeout", 30) or 30)

    # Set flags based on template parameters
    invert = template.get("invert", "") not in ["", "false", False]
    headless = template.get("headless", "") not in ["", "false", False]
    dark = template.get("dark", "") not in ["", "false", False]
    stealth = template.get("stealth", "") not in ["", "false", False]
    browser = template.get("browser", "") not in ["", "false", False]
    danger = template.get("danger", "") not in ["", "false", False]
    danger_fallback = _danger_fallback_active(url)

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
        elif scheme == "rtmp":
            port = 1935
        else:
            port = 80

    rtsp_preflight_ok = False
    rtsp_preflight_url = None
    lan_fast_reachable: bool | None = None

    if domain and _is_lan_target(domain):
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
        candidate_ports: list[int] = []
        if scheme == "http":
            candidate_ports = [80]
        elif scheme == "https":
            candidate_ports = [443]
        elif scheme == "rtsp":
            candidate_ports = [554]
        elif port is not None:
            candidate_ports = [int(port)]
        if port is not None and int(port) not in candidate_ports:
            candidate_ports.append(int(port))

        fast_timeout = max(0.2, float(PREFLIGHT_LAN_FAST_PROBE_TIMEOUT))
        lan_fast_reachable = False
        for probe_port in candidate_ports:
            if is_address_reachable(domain, port=probe_port, timeout=fast_timeout):
                lan_fast_reachable = True
                break
        if not lan_fast_reachable:
            logging.info(
                "Fast LAN preflight blocked %s (ports=%s)",
                clean_url,
                ",".join(str(p) for p in candidate_ports),
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
    if cached_http_error in {403, 404, 410}:
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

    def _weatherbug_extract_latest_image(page_url: str) -> str | None:
        """Extract the current camera still from a WeatherBug camera page."""

        if not re.findall(
            r"^https?://(www\.)?weatherbug\.com/weather-camera\?cam=",
            page_url,
            flags=re.I,
        ):
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
            body = resp.text or ""
        finally:
            resp.close()

        # Prefer the structured JSON field for the currently featured camera.
        m = re.search(
            r"\"image\"\\s*:\\s*\"(https://cameras-cam\\.cdn\\.weatherbug\\.net/[^\\\"]+?_l\\.jpg)\"",
            body,
        )
        if m:
            return m.group(1)

        # Fall back to any preload image reference.
        m = re.search(
            r"rel=\\\"preload\\\"\\s+as=\\\"image\\\"\\s+href=\\\"(https://cameras-cam\\.cdn\\.weatherbug\\.net/[^\\\"]+?_l\\.jpg)\\\"",
            body,
        )
        if m:
            return m.group(1)
        return None

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
                logging.info("HTML stable; skipping heavy render for %s", clean_url)
                _record_tier_success(url, TIER_HTTP, "html_not_modified")
                _clear_danger_fallback(url)
                return True
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

    # check if modified.
    if is_modified is False and not danger and not browser:
        cas_error(url)
        _record_tier_success(url, TIER_HTTP, "not_modified")
        _clear_danger_fallback(url)
        return True  # content has not changed...

    # Attempt to download or capture based on content type and URL
    if content_type.startswith("text/html") and not danger:
        img_url = _weatherbug_extract_latest_image(url)
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
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "weatherbug_image_extracted")
                _set_method_preference(url, "snapshot")
                _clear_danger_fallback(url)
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
        )
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "image_downloaded")
            _clear_danger_fallback(url)
            return lsuc
        cas_error(url)
        _record_tier_failure(url, TIER_HTTP, "image_download_failed")

    if is_pdf_url(url, content_type) and not danger and not browser:
        lsuc = download_pdf(
            url, output_path, timeout, name, invert, dark, stealth, username, password
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
                        )
                        if lsuc is True:
                            _record_tier_success(url, TIER_HTTP, "snapshot_downloaded")
                            _set_method_preference(url, "snapshot")
                            _clear_danger_fallback(url)
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
        snapshot_url = None
        if urlparse(url).scheme.lower() == "rtsp":
            snapshot_url = _probe_snapshot_url(rtsp_url, username, password)
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
            )
            if lsuc is True:
                _record_tier_success(url, TIER_HTTP, "snapshot_downloaded")
                _set_method_preference(url, "snapshot")
                _clear_danger_fallback(url)
                return lsuc
        lsuc = capture_frame_from_stream(rtsp_url, output_path, timeout, name, invert)
        if lsuc is True:
            _record_tier_success(url, TIER_HTTP, "stream_captured")
            _record_method_success(url, "stream")
            _set_method_preference(url, "stream")
            _clear_danger_fallback(url)
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
        lsuc = capture_frame_with_ytdlp(url, output_path, name, invert)
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
                url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
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
                url, output_path, timeout, name, invert, template.get("proxy"), dark
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
                url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
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
            )
            if lsuc is True:
                detail = "danger_capture" if use_danger else "headless_capture"
                _record_tier_success(url, target_tier, detail)
                _record_method_success(url, "headless")
                _set_method_preference(url, "headless")
                _clear_renderer_failure("headless")
                _clear_danger_fallback(url)
                return lsuc

            if not use_danger:
                cas_error(url)
                if time.time() - method_start > timeout:
                    _record_renderer_failure("headless", "timeout")
                    _record_browser_failure_for_danger(url, "headless_timeout")
                    record_preflight_backoff(
                        url, "browser_timeout", PREFLIGHT_BACKOFF_BROWSER_FAIL
                    )
                    _record_tier_failure(url, target_tier, "browser_timeout")
                    _record_method_failure(url, "headless", HEADLESS_BACKOFF_BASE)
                else:
                    _record_renderer_failure("headless", "failed")
                    _record_browser_failure_for_danger(url, "headless_failed")
                    _record_tier_failure(url, target_tier, "browser_failed")
                    _record_method_failure(url, "headless", HEADLESS_BACKOFF_BASE)

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

    # Disallow local file paths to avoid unintended file disclosure
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {"http", "https", "rtsp", "rtmp"}:
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
    ):  # try every 1 hour no matter what??
        _record_tier_failure(url, TIER_OFFLINE, "cached_bad")
        return False

    cached_status = get_cached_status_code(url)
    if cached_status is not None and cached_status >= 400:
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
        prev = etag_cache.get(url)
        if prev and prev != etag:
            now = time.time()
            entry = etag_flip_cache.setdefault(url, {"count": 0, "first": now})
            if now - entry.get("first", now) > PREFLIGHT_ETAG_FLIP_WINDOW:
                entry["count"] = 0
                entry["first"] = now
            entry["count"] = entry.get("count", 0) + 1
            if entry["count"] >= PREFLIGHT_ETAG_FLIP_THRESHOLD:
                record_preflight_backoff(url, "etag_flip", PREFLIGHT_ETAG_FLIP_BACKOFF)
            etag_flip_cache[url] = entry
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
        if delta > PREFLIGHT_CONTENT_LENGTH_MAX_VARIANCE:
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
        port = parsed.port or 554
        return f"{parsed.hostname.lower()}:{port}"
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
    port = parsed.port or 554
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
        sock.settimeout(timeout)
        sock.sendall(_serialize(headers))
        response = sock.recv(4096).decode("ascii", errors="ignore")
        status_line = response.splitlines()[0] if response else ""
        status = int(status_line.split(" ")[1]) if "RTSP/1.0" in status_line else 0
        header_map = {}
        for line in response.splitlines()[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            header_map[key.strip()] = value.strip()
        if status == 401 and username and password:
            auth_header = _rtsp_build_auth(
                method, uri, header_map.get("WWW-Authenticate"), username, password
            )
            if auth_header:
                headers["CSeq"] = "2"
                headers["Authorization"] = auth_header
                sock.sendall(_serialize(headers))
                response = sock.recv(4096).decode("ascii", errors="ignore")
                status_line = response.splitlines()[0] if response else ""
                status = (
                    int(status_line.split(" ")[1]) if "RTSP/1.0" in status_line else 0
                )
                header_map = {}
                for line in response.splitlines()[1:]:
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    header_map[key.strip()] = value.strip()
                return status, response, header_map
        return status, response, header_map
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
    for line in response.splitlines():
        if line.startswith("m=video"):
            # Some cameras announce recvonly SDP with media port 0 but still
            # provide playable video tracks. Presence of m=video is enough.
            has_video = True
        if line.startswith("a=rtpmap:"):
            parts = line.split(" ", 1)
            if len(parts) == 2:
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
    try:
        resp = http_session().get(url, **request_kwargs)
        ctype = resp.headers.get("Content-Type", "").lower()
        if "multipart" in ctype and "boundary=" in ctype:
            if _validate_mjpeg_frame(resp):
                _set_mjpeg_probe(url, True)
                resp.close()
                return True
            resp.close()
            _set_mjpeg_probe(url, False)
            return False
        chunk = b""
        try:
            chunk = next(resp.iter_content(chunk_size=1024))
        except Exception:
            chunk = b""
        if b"--" in chunk or b"\xff\xd8" in chunk:
            if _validate_mjpeg_frame(resp):
                _set_mjpeg_probe(url, True)
                resp.close()
                return True
        resp.close()
    except Exception:
        pass
    _set_mjpeg_probe(url, False)
    return False


def _validate_mjpeg_frame(response) -> bool:
    boundary = None
    ctype = response.headers.get("Content-Type", "")
    match = re.search(r"boundary=([^;]+)", ctype, re.I)
    if match:
        boundary = match.group(1).strip().strip('"').encode("utf-8")
    try:
        for chunk in response.iter_content(chunk_size=2048):
            if not chunk:
                continue
            if boundary and boundary not in chunk and b"\xff\xd8" not in chunk:
                continue
            if b"\xff\xd8" in chunk:
                return True
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
    if cached and dns_cache_time.get(key, 0) > time.time() - PREFLIGHT_DNS_CACHE_TTL:
        return cached, "dns_cache"

    try:
        socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
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

    cached_tls = tls_cache.get(key)
    if (
        cached_tls
        and tls_cache_time.get(key, 0) > time.time() - PREFLIGHT_TLS_CACHE_TTL
    ):
        return cached_tls, "tls_cache"

    try:
        context = ssl.create_default_context()
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
                    auth = get_digest_auth(url)
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
    auth_match = re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url)
    if auth_match:
        return requests.auth.HTTPBasicAuth(*auth_match[0])
    if username and password:
        return requests.auth.HTTPBasicAuth(username, password)
    return None


def get_digest_auth(url, username=None, password=None):
    """Return :class:`HTTPDigestAuth` if credentials are available."""
    auth_match = re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url)
    if auth_match:
        return requests.auth.HTTPDigestAuth(*auth_match[0])
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
    video_indicators = [".mjpg", ".mp4", ".gif", ".webp", "rtsp://", ".m3u8", ":5004/"]
    return (
        any(ind in url.lower() for ind in video_indicators) or "video/" in content_type
    )


def should_use_lightweight_browser(
    url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
):
    """Determine if a lightweight browser should be used for capture."""

    # print("   <<<<", dedicated_selector, "pop", popup_xpath, "stealth", stealth, browser, is_enhanced(url), danger)
    return (
        re.findall(r"^https?://", url, flags=re.I)
        and dedicated_selector in [None, ""]
        and popup_xpath in [None, ""]
        and not stealth
        and not browser
        and not headless
        and not is_enhanced(url)
        and not danger
    )


def should_use_phantom_browser(
    url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
):
    """Determine if a lightweight browser should be used for capture."""
    return (
        re.findall(r"^https?://", url, flags=re.I)
        # dedicated_selector in [None, ""] and
        # popup_xpath in [None, ""] and
        and not stealth
        and not browser
        and not is_enhanced(url)
        and not danger
    )


# The rest of the functions (download_image, download_pdf, capture_frame_from_stream,
# capture_frame_with_ytdlp, capture_screenshot_and_har_light, capture_screenshot_and_har)
# should be implemented as before, with appropriate error handling and logging.


def capture_frame_with_ytdlp(url, output_path, name="unknown", invert=False):
    """
    Use yt-dlp to get the video URL, then ffmpeg to capture a single frame from that video.
    """
    # Quick check for yt-dlp
    if shutil.which("yt-dlp") is None:
        logging.error("yt-dlp is not installed or not in the system path.")
        return False
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
        # 1) Preflight with yt-dlp simulate to avoid heavy work on dead streams.
        if PREFLIGHT_YTDLP_SIMULATE:
            simulate_cmd = [
                "yt-dlp",
                "--simulate",
                "--skip-download",
                "--no-warnings",
                "--quiet",
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
                lurl_cache[url] = "bad"
                return False

        # 2) Use yt-dlp to retrieve the direct video URL
        ytdlp_command = [
            "yt-dlp",
            "--get-url",
            # "--format",
            # "bestvideo",  # note, don't specify this or it will screw up on streams without audio (common)
            url,
        ]
        result = subprocess.run(
            ytdlp_command,
            # check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CAPTURE_TIMEOUT,
            check=False,
        )

        # Note! check the result. If the return code isnt 0, then we should fail out.  Why though? Check on that too.

        if result.returncode != 0:
            lurl_cache[url] = "bad"
            if re.findall(
                r"(?:vailable|found|404)", result.stderr.decode("utf-8").lower()
            ):
                lurl_cache[url] = "offline"
                # print("offline", url)
            return False

        lurl_cache[url] = "good"
        video_url = result.stdout.decode().strip()

        # Validate the video_url to ensure it is a legitimate URL
        parsed_url = urlparse(video_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logging.error(f"Invalid video URL: {video_url}")
            return False

        # 2) Use ffmpeg to capture a single frame
        ffmpeg_command = [FFMPEG_PATH]
        if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
            ffmpeg_command += ["-hwaccel", FFMPEG_HWACCEL]
        ffmpeg_command += [
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


def capture_frame_from_stream(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    stealth=False,
):
    """Use ffmpeg to capture multiple frames from a video stream and save the last one."""
    if not _check_ffmpeg():
        return False

    scheme = urlparse(url).scheme.lower()
    probe_timeout = max(min(timeout, STREAM_PROBE_TIMEOUT), 3)
    if not _probe_stream_with_ffprobe(url, probe_timeout, name):
        record_preflight_backoff(url, "ffprobe_failed", PREFLIGHT_BACKOFF_STREAM_FAIL)
        return False
    if PREFLIGHT_FFMPEG_NULL_PROBE:
        if not _ffmpeg_null_probe(url, probe_timeout, name, stealth):
            record_preflight_backoff(
                url, "ffmpeg_null_probe_failed", PREFLIGHT_BACKOFF_STREAM_FAIL
            )
            return False

    clean_url = sanitize_url(url)
    is_hdhomerun_stream = _is_hdhomerun_like_stream_url(url)

    timeout = max(timeout, 5)
    if is_hdhomerun_stream:
        # Give tuner-backed streams extra startup room before declaring failure.
        timeout = max(timeout, 15)

    tmpdirname = f"/tmp/glimpser_{name}"
    os.makedirs(tmpdirname, exist_ok=True)
    if os.path.exists(tmpdirname):
        transports = [None]
        if scheme == "rtsp":
            transports = _rtsp_transport_candidates(url)
        per_attempt_timeout = max(5, int(timeout / max(len(transports), 1)))

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
            ]
            if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
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
            elif scheme == "rtsp":
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

            # Use configured analyze duration and probe size values
            command.extend(["-analyzeduration", analyze_duration])
            command.extend(["-probesize", probe_size])
            frames_to_capture = NUM_FRAMES
            if is_hdhomerun_stream:
                # HDHomeRun feeds may have sparse keyframes; decode non-key
                # frames too and keep capture burst short for responsiveness.
                frames_to_capture = max(1, min(NUM_FRAMES, 2))
            command.extend(
                [
                    "-use_wallclock_as_timestamps",
                    "1",
                    #'-ec', '15',
                    "-threads",
                    "1",
                    "-sn",
                    "-an",
                    #'-err_detect','aggressive',
                    "-i",
                    url,  # Input stream URL
                    "-movflags",
                    "+faststart",
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
            if not is_hdhomerun_stream:
                command.extend(["-skip_frame", "nokey"])

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
                    "ffmpeg timed out for %s after %ss", clean_url, per_attempt_timeout
                )
                continue
            except subprocess.CalledProcessError as e:
                logging.error(
                    "ffmpeg failed for %s: %s",
                    clean_url,
                    e.stderr.decode("utf-8", "ignore")[:200],
                )
                continue
            except Exception as e:
                logging.error("Error running ffmpeg for %s: %s", clean_url, e)
                continue

            try:
                # Sort the captured frames by size and take the last one
                frames = sorted(
                    os.listdir(tmpdirname),
                    key=lambda x: os.path.getsize(os.path.join(tmpdirname, x)),
                )
                if frames:
                    last_frame_path = os.path.join(tmpdirname, frames[-1])
                    # Move the last frame to the output path
                    shutil.move(last_frame_path, output_path)
                    if os.path.exists(output_path) and _is_valid_png(output_path):
                        add_timestamp(output_path, name=name, invert=invert)
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
            if is_mostly_blank(image):
                logging.warning(
                    f"Captured image is mostly blank—skipping. {clean_url} {name}"
                )
                record_preflight_backoff(
                    url, "lightweight_blank", PREFLIGHT_BACKOFF_BROWSER_FAIL
                )
                os.unlink(tmp_path)
                return False

            image = remove_background(image)
            if dark:
                image = apply_dark_mode(image)
            image.save(tmp_path, "PNG")

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
    """Kills the Chrome process associated with the given driver."""
    try:
        time.sleep(5)
        if driver.service.process and driver.service.process.pid:
            pid = driver.service.process.pid
            chrome_process = psutil.Process(pid)
            for child in chrome_process.children(recursive=True):
                if psutil.pid_exists(child.pid):
                    child.terminate()
                    child.wait(timeout=5)
            if psutil.pid_exists(pid):
                chrome_process.terminate()
                logging.debug("TERMINATE %s", driver)
                chrome_process.wait(timeout=5)
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
    This helps if your program crashed and left behind /tmp/glimpser_XYZ directories.
    """
    now = time.time()
    tmp_root = "/tmp"
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


########################################
# The "Tough" capture_screenshot_and_har
########################################


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
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        logging.error(
            f"[capture_screenshot_and_har] Not a valid http/https URL: {clean_url}"
        )
        return False

    if not is_system_online():
        logging.warning("System offline; skipping capture for %s", clean_url)
        return False

    timeout = max(timeout, 30)

    cleanup_old_tempdirs(prefix="glimpser_", max_age_hours=12)

    chrome_path = get_chrome_path()
    if chrome_path is None or not os.path.exists(chrome_path):
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
                url=url,
                clean_url=clean_url,
            )

    ##################
    # Non-Danger Mode
    ##################
    user_data_dir = None
    driver = None
    try:
        # Create unique ephemeral profile dir in /tmp
        tmp_profile = tempfile.mkdtemp(prefix="glimpser_")
        user_data_dir = tmp_profile  # just to keep track

        # Using undetected_chromedriver for stealth:
        # driver_options = uc.ChromeOptions()
        driver_options = Options()
        if headless:
            # For Chrome 109+, "headless=new" is recommended; fallback if it fails
            driver_options.add_argument("--headless=new")

        # Key ephemeral & performance log settings
        driver_options.add_argument(f"--user-data-dir={tmp_profile}")
        driver_options.add_argument("--no-sandbox")
        driver_options.add_argument("--disable-dev-shm-usage")
        driver_options.add_argument("--disable-gpu")
        if (
            _hwaccel_enabled()
            and config._machine_supports_hwaccel()
            and browser_supports_gl(chrome_path)
        ):
            driver_options.add_argument("--use-gl=egl")
        if stealth:
            apply_stealth_options(driver_options)
        else:
            driver_options.add_argument("--window-size=1920,1080")
            driver_options.add_argument("--disable-blink-features=AutomationControlled")
            driver_options.add_argument("--enable-automation")
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

        driver = launch_headless_chrome(driver_options, version=version)
        if driver is None:
            _purge_driver_cache()
            driver = launch_headless_chrome(driver_options, version)
            if driver is None:
                logging.error("missing driver!")
                raise ValueError("missing driver!")

        driver.set_page_load_timeout(timeout)
        # Attempt dark mode for the loaded page, if desired
        if dark and not invert:
            try:
                driver.execute_cdp_cmd(
                    "Emulation.setAutoDarkModeOverride", {"enabled": True}
                )
            except Exception as e:
                logging.debug(f"Failed to setAutoDarkModeOverride: {e}")

        # Navigate
        driver.get(url)
        time.sleep(
            5
        )  # Basic wait for DOM. Tweak as needed or switch to explicit waits.

        # Remove popups
        if popup_xpath:
            try:
                _remove_popup(driver, popup_xpath)
            except Exception:
                # logging.info(f"Could not remove popup={popup_xpath}:")
                pass

        # If dedicated_selector is set, capture that region instead of full page
        if dedicated_selector:
            try:
                element = driver.find_element(By.XPATH, dedicated_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)
                element.screenshot(partial_screenshot)
            except Exception:
                pass

        # Fallback to entire page if partial didn't get created
        if not os.path.exists(partial_screenshot):
            driver.save_screenshot(partial_screenshot)

        # Attempt to gather performance logs → HAR
        # if har_output_path:
        #    _save_har_logs(driver, har_output_path)

        # Post-process final
        success = _finalize_screenshot(
            partial_screenshot,
            output_path,
            name,
            invert,
            dark,
            url=url,
            clean_url=clean_url,
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
                time.sleep(1)
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
    url: str | None = None,
    clean_url: str | None = None,
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

            blank = is_mostly_blank(img)
            if blank:
                logging.warning(f"[{name}] The captured screenshot looks mostly blank.")
                if url:
                    record_preflight_backoff(
                        url, "blank_capture", PREFLIGHT_BACKOFF_BROWSER_FAIL
                    )
                orig_path = final_path + ".orig.png"
                _safe_move(tmp_path, orig_path)
                create_placeholder(tmp_path, name)
                success = False
            else:
                # Optional background removal
                img = remove_background(img)

                # If you want to do naive “darkening” or inverting more thoroughly,
                # you can do that here. For example:
                # if dark:
                #    img = apply_dark_mode(img)

                # Save back
                img.save(tmp_path, "PNG")
                success = True

        # Now add a timestamp overlay. If this fails the file may be removed.
        add_timestamp(tmp_path, name=name, invert=invert)

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
        logging.debug("trying %s", clean_url)
        driver.get(url)
        logging.debug("success, screenshotting %s", clean_url)
        _send_input_event()
        time.sleep(3)

        # Attempt dark mode if desired
        if dark and not invert:
            try:
                driver.execute_cdp_cmd(
                    "Emulation.setAutoDarkModeOverride", {"enabled": True}
                )
            except Exception as e:
                logging.debug(f"[danger_mode] setAutoDarkModeOverride failed: {e}")
        time.sleep(5)

        # Remove popups
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


def _remove_popup(driver, popup_xpath):
    """
    If there's an annoying overlay or popup, remove it from the DOM by XPATH.
    """
    try:
        elements = driver.find_elements(By.XPATH, popup_xpath)
        for el in elements:
            driver.execute_script("arguments[0].remove();", el)
    except Exception as e:
        logging.debug(f"_remove_popup error: {e}")


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
    image.save(image_path, "PNG")
    add_timestamp(image_path, name=name)

    return image_path
