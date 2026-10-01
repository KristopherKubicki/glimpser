"""Validate configuration values such as URLs, groups and settings.

The helpers sanitize user supplied data for safe storage and provide
reasonable defaults.  They are reused across route handlers, CLI tools
and database updates to keep validation logic consistent.
"""

import json
import os
import re
import socket
from ipaddress import ip_address
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from werkzeug.utils import secure_filename

TRUTHY_STRINGS = {"true", "1", "t", "y", "yes", "on"}
FALSEY_STRINGS = {"false", "0", "f", "n", "no", "off"}
BOOL_STRINGS = {
    "true",
    "false",
    "on",
    "off",
    "yes",
    "no",
    "y",
    "n",
    "t",
    "f",
}

EVENT_BUFFER_DEFAULTS = {
    "event_buffer_fps": 1,
    "event_buffer_seconds": 120,
    "event_buffer_width": 640,
    "event_buffer_pre_seconds": 8,
    "event_buffer_post_seconds": 6,
    "event_buffer_backoff_seconds": 300,
}
EVENT_BUFFER_FORMATS = {"gif", "mp4"}


def to_bool(value: object) -> bool:
    """Return ``True`` when *value* represents a truthy string."""

    return str(value).strip().lower() in TRUTHY_STRINGS


def is_bool_string(value: object) -> bool:
    """Return ``True`` when ``value`` looks like a boolean string."""

    return str(value).strip().lower() in BOOL_STRINGS


def validate_proxy(proxy: str | None) -> str | None:
    """Return the proxy string if valid, otherwise ``None``.

    A valid proxy must start with ``http://`` or ``https://``. Whitespace-only
    values are ignored.
    """

    if proxy is None:
        return None

    proxy = str(proxy).strip()

    if not proxy:
        return None

    if not re.match(r"^https?://", proxy, flags=re.IGNORECASE):
        return None

    parsed = urlparse(proxy)
    if not parsed.netloc:
        return None

    return proxy


def validate_url(url: str | None) -> str | None:
    """Return the URL string if valid, otherwise ``None``.

    The URL must use the ``http`` or ``https`` scheme and must not contain
    newline characters or start with a dash. This helps prevent accidental
    command-line argument injection when the value is passed to subprocess
    calls.
    """

    if url is None:
        return None

    url = str(url).strip()

    if not url or url.startswith("-"):
        return None

    if "\n" in url or "\r" in url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    if not parsed.netloc:
        return None

    return url


def _is_private_host(host: str) -> bool:
    """Return ``True`` when *host* is a private or local address."""

    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ip_address(host)
    except ValueError:  # not an IP address
        return host.endswith(".local")
    return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local


def is_public_url(url: str) -> bool:
    """Return ``True`` when *url* points to a non-local address."""

    try:
        host = urlparse(url).hostname
    except Exception:
        return False
    if not host:
        return False
    if _is_private_host(host):
        return False
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return bool(addresses) and all(
            ip_address(address[4][0]).is_global for address in addresses
        )
    except (OSError, ValueError):
        return False


def _bounded_int(
    value: object,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Return an integer clamped to an inclusive range."""

    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _is_loopback_host(host: str) -> bool:
    """Return ``True`` for loopback names and addresses."""

    normalized = str(host or "").strip().strip("[]").lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_lan_camera_host(host: str) -> bool:
    """Return ``True`` when *host* looks like a LAN camera endpoint."""

    normalized = str(host or "").strip().strip("[]").lower()
    if not normalized or _is_loopback_host(normalized):
        return False
    if normalized.endswith(".home.arpa"):
        return True
    return _is_private_host(normalized)


def event_buffer_eligibility(data: dict) -> tuple[bool, str]:
    """Return whether template data is eligible for LAN event buffering."""

    url = str(data.get("url") or "").strip()
    if not url:
        return False, "URL is required"

    if str(data.get("source_template") or "").strip():
        return False, "source-template views are derived, not direct cameras"
    if to_bool(data.get("browser", False)) or to_bool(data.get("stealth", False)):
        return False, "browser captures are not direct LAN camera streams"
    if validate_proxy(data.get("proxy")):
        return False, "proxied captures are not eligible for local buffering"

    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https", "rtsp"}:
        return False, "only HTTP(S) or RTSP LAN camera URLs are eligible"
    if not parsed.hostname:
        return False, "URL must include a host"
    if not _is_lan_camera_host(parsed.hostname):
        return False, "host must be a private LAN camera address"

    return True, "eligible"


def normalize_event_buffer_settings(data: dict, sanitized: dict) -> None:
    """Validate and copy LAN event-buffer settings into *sanitized*."""

    enabled = to_bool(data.get("event_buffer_enabled", False))
    profile = str(data.get("event_buffer_profile") or "lan_hardwired").strip().lower()
    if profile in {"", "off"}:
        profile = "lan_hardwired"
    if profile != "lan_hardwired":
        raise ValueError("event_buffer_profile is invalid")

    fps = _bounded_int(
        data.get("event_buffer_fps"), EVENT_BUFFER_DEFAULTS["event_buffer_fps"], 1, 2
    )
    seconds = _bounded_int(
        data.get("event_buffer_seconds"),
        EVENT_BUFFER_DEFAULTS["event_buffer_seconds"],
        30,
        300,
    )
    width = _bounded_int(
        data.get("event_buffer_width"),
        EVENT_BUFFER_DEFAULTS["event_buffer_width"],
        320,
        1280,
    )
    pre_seconds = _bounded_int(
        data.get("event_buffer_pre_seconds"),
        EVENT_BUFFER_DEFAULTS["event_buffer_pre_seconds"],
        0,
        30,
    )
    post_seconds = _bounded_int(
        data.get("event_buffer_post_seconds"),
        EVENT_BUFFER_DEFAULTS["event_buffer_post_seconds"],
        1,
        30,
    )
    backoff_seconds = _bounded_int(
        data.get("event_buffer_backoff_seconds"),
        EVENT_BUFFER_DEFAULTS["event_buffer_backoff_seconds"],
        30,
        1800,
    )
    if pre_seconds >= seconds:
        pre_seconds = max(seconds - 1, 0)
    if post_seconds > seconds:
        post_seconds = seconds

    output_format = str(data.get("event_buffer_format") or "gif").strip().lower()
    if output_format not in EVENT_BUFFER_FORMATS:
        raise ValueError("event_buffer_format is invalid")

    if enabled:
        eligible, reason = event_buffer_eligibility({**data, **sanitized})
        if not eligible:
            raise ValueError(f"event_buffer_enabled requires {reason}")

    sanitized["event_buffer_enabled"] = enabled
    sanitized["event_buffer_profile"] = "lan_hardwired" if enabled else ""
    sanitized["event_buffer_fps"] = fps
    sanitized["event_buffer_seconds"] = seconds
    sanitized["event_buffer_width"] = width
    sanitized["event_buffer_pre_seconds"] = pre_seconds
    sanitized["event_buffer_post_seconds"] = post_seconds
    sanitized["event_buffer_format"] = output_format
    sanitized["event_buffer_backoff_seconds"] = backoff_seconds


def validate_template_name(template_name: str):
    """Return sanitized template name if valid, otherwise ``None``."""
    if template_name is None or not isinstance(template_name, str):
        return None

    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
    )
    if not all(char in allowed_chars for char in template_name):
        return None

    if len(template_name) == 0 or len(template_name) > 32:
        return None

    if template_name[0] in "-_." or template_name[-1] in "-_.":
        return None
    if ".." in template_name:
        return None
    if "--" in template_name:
        return None
    if "__" in template_name:
        return None

    sanitized_name = secure_filename(template_name)
    if sanitized_name != template_name:
        return None

    return sanitized_name


def validate_group_name(group_name: str | None) -> str | None:
    """Return sanitized group name if valid, otherwise ``None``.

    Group names must be at least two characters after trimming
    whitespace and replacing it with underscores.
    """

    if group_name is None or not isinstance(group_name, str):
        return None

    sanitized = re.sub(r"\s+", "_", group_name.strip()).lower()
    if len(sanitized) < 2:
        return None
    if not sanitized:
        return None

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if not all(ch in allowed for ch in sanitized):
        return None

    if sanitized[0] in "-_" or sanitized[-1] in "-_":
        return None
    if ".." in sanitized or "--" in sanitized or "__" in sanitized:
        return None

    secure = secure_filename(sanitized)
    if secure != sanitized or len(secure) > 32:
        return None

    return secure


def validate_update_data(data: dict) -> dict:
    """Validate and normalize template update data.

    Missing or invalid values fall back to safe defaults. Raises
    ``ValueError`` when required fields are absent.
    """

    sanitized = {}

    stealth_flag = str(data.get("stealth", False)).lower() in {
        "true",
        "1",
        "t",
        "y",
        "yes",
        "on",
    }
    browser_flag = str(data.get("browser", False)).lower() in {
        "true",
        "1",
        "t",
        "y",
        "yes",
        "on",
    }

    default_frequency = 60 if stealth_flag or browser_flag else 30
    default_timeout = 30 if stealth_flag or browser_flag else 10

    source_template = validate_template_name(
        str(data.get("source_template") or "").strip()
    )
    if str(data.get("source_template") or "").strip() and not source_template:
        raise ValueError("source_template is invalid")
    sanitized["source_template"] = source_template or ""

    url = (data.get("url") or "").strip()
    if not url and not sanitized["source_template"]:
        raise ValueError("url is required")
    sanitized["url"] = url

    try:
        frequency = int(data.get("frequency", default_frequency) or default_frequency)
    except (TypeError, ValueError):
        frequency = default_frequency
    frequency = max(frequency, 1)
    frequency = min(frequency, 525600)
    sanitized["frequency"] = frequency

    try:
        timeout = int(data.get("timeout", default_timeout) or default_timeout)
    except (TypeError, ValueError):
        timeout = default_timeout
    timeout = max(timeout, 1)
    max_timeout = frequency * 60
    if timeout >= max_timeout:
        timeout = max_timeout - 1
    sanitized["timeout"] = timeout

    try:
        rollback = int(data.get("rollback_frames", 0) or 0)
    except (TypeError, ValueError):
        rollback = 0
    rollback = max(rollback, 0)
    sanitized["rollback_frames"] = rollback

    try:
        confidence = float(data.get("object_confidence", 0.5) or 0.5)
    except (TypeError, ValueError):
        confidence = 0.5
    if confidence < 0:
        confidence = 0.0
    if confidence > 1:
        confidence = 1.0
    sanitized["object_confidence"] = confidence

    try:
        motion = float(data.get("motion", 0.2) or 0.2)
    except (TypeError, ValueError):
        motion = 0.2
    if motion < 0:
        motion = 0.0
    if motion > 1:
        motion = 1.0
    sanitized["motion"] = motion

    stabilize_mode = str(data.get("stabilize_mode") or "").strip().lower()
    if stabilize_mode not in {"", "off", "previous", "rolling_5m", "rolling_30m"}:
        raise ValueError("stabilize_mode is invalid")
    sanitized["stabilize_mode"] = (
        "" if stabilize_mode in {"", "off"} else stabilize_mode
    )

    try:
        capture_rotate_degrees = int(data.get("capture_rotate_degrees") or 0)
    except (TypeError, ValueError):
        raise ValueError("capture_rotate_degrees is invalid") from None
    if capture_rotate_degrees == 270:
        capture_rotate_degrees = -90
    elif capture_rotate_degrees == -270:
        capture_rotate_degrees = 90
    elif capture_rotate_degrees == -180:
        capture_rotate_degrees = 180
    if capture_rotate_degrees not in {-90, 0, 90, 180}:
        raise ValueError("capture_rotate_degrees is invalid")
    sanitized["capture_rotate_degrees"] = capture_rotate_degrees

    night_enhance_mode = str(data.get("night_enhance_mode") or "").strip().lower()
    if night_enhance_mode not in {"", "off", "light", "medium", "strong"}:
        raise ValueError("night_enhance_mode is invalid")
    sanitized["night_enhance_mode"] = (
        "" if night_enhance_mode in {"", "off"} else night_enhance_mode
    )

    deflicker_mode = str(data.get("deflicker_mode") or "").strip().lower()
    if deflicker_mode not in {"", "off", "light", "medium", "strong"}:
        raise ValueError("deflicker_mode is invalid")
    sanitized["deflicker_mode"] = (
        "" if deflicker_mode in {"", "off"} else deflicker_mode
    )

    burst_enhance_mode = str(data.get("burst_enhance_mode") or "").strip().lower()
    if burst_enhance_mode not in {"", "off", "full_frame", "roi"}:
        raise ValueError("burst_enhance_mode is invalid")
    sanitized["burst_enhance_mode"] = (
        "" if burst_enhance_mode in {"", "off"} else burst_enhance_mode
    )

    burst_enhance_profile = str(data.get("burst_enhance_profile") or "").strip().lower()
    if burst_enhance_profile not in {"", "clean", "hybrid", "crisp"}:
        raise ValueError("burst_enhance_profile is invalid")
    sanitized["burst_enhance_profile"] = (
        "" if not burst_enhance_profile else burst_enhance_profile
    )

    burst_enhance_roi = str(data.get("burst_enhance_roi") or "").strip()
    if len(burst_enhance_roi) > 255:
        raise ValueError("burst_enhance_roi is too long")
    if burst_enhance_roi and not re.fullmatch(r"[0-9.,;\s-]+", burst_enhance_roi):
        raise ValueError("burst_enhance_roi is invalid")
    sanitized["burst_enhance_roi"] = burst_enhance_roi

    capture_crop_roi = str(data.get("capture_crop_roi") or "").strip()
    if len(capture_crop_roi) > 255:
        raise ValueError("capture_crop_roi is too long")
    if capture_crop_roi and not re.fullmatch(r"[0-9.,;\s-]+", capture_crop_roi):
        raise ValueError("capture_crop_roi is invalid")
    sanitized["capture_crop_roi"] = capture_crop_roi

    lens_correction_spec = str(data.get("lens_correction_spec") or "").strip()
    if len(lens_correction_spec) > 255:
        raise ValueError("lens_correction_spec is too long")
    if lens_correction_spec and not re.fullmatch(
        r"[A-Za-z0-9_=.,;:\s-]+", lens_correction_spec
    ):
        raise ValueError("lens_correction_spec is invalid")
    sanitized["lens_correction_spec"] = lens_correction_spec

    horizon_level_mode = str(data.get("horizon_level_mode") or "").strip().lower()
    if horizon_level_mode not in {"", "off", "roll", "smooth"}:
        raise ValueError("horizon_level_mode is invalid")
    sanitized["horizon_level_mode"] = (
        "" if horizon_level_mode in {"", "off"} else horizon_level_mode
    )

    horizon_level_roi = str(data.get("horizon_level_roi") or "").strip()
    if len(horizon_level_roi) > 255:
        raise ValueError("horizon_level_roi is too long")
    if horizon_level_roi and not re.fullmatch(r"[0-9.,;\s-]+", horizon_level_roi):
        raise ValueError("horizon_level_roi is invalid")
    sanitized["horizon_level_roi"] = horizon_level_roi

    composite_view_mode = str(data.get("composite_view_mode") or "").strip().lower()
    if composite_view_mode not in {"", "off", "grid", "hero_strip"}:
        raise ValueError("composite_view_mode is invalid")
    sanitized["composite_view_mode"] = (
        "" if composite_view_mode in {"", "off"} else composite_view_mode
    )

    composite_view_spec = str(data.get("composite_view_spec") or "").strip()
    if len(composite_view_spec) > 1000:
        raise ValueError("composite_view_spec is too long")
    if composite_view_spec and not re.fullmatch(
        r"[A-Za-z0-9 _.\-@,;]+", composite_view_spec
    ):
        raise ValueError("composite_view_spec is invalid")
    sanitized["composite_view_spec"] = composite_view_spec

    normalize_event_buffer_settings(data, sanitized)

    for key, min_value, max_value in [
        ("camera_latitude", -90.0, 90.0),
        ("view_target_latitude", -90.0, 90.0),
        ("camera_longitude", -180.0, 180.0),
        ("view_target_longitude", -180.0, 180.0),
    ]:
        raw_value = data.get(key)
        if raw_value in {None, ""}:
            sanitized[key] = None
            continue
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} is invalid") from None
        if not min_value <= numeric_value <= max_value:
            raise ValueError(f"{key} is invalid")
        sanitized[key] = numeric_value

    elevation_value = data.get("camera_elevation_m")
    if elevation_value in {None, ""}:
        sanitized["camera_elevation_m"] = None
    else:
        try:
            sanitized["camera_elevation_m"] = float(elevation_value)
        except (TypeError, ValueError):
            raise ValueError("camera_elevation_m is invalid") from None

    for key in ("camera_location_label", "view_target_label"):
        label = str(data.get(key) or "").strip()
        if len(label) > 255:
            raise ValueError(f"{key} is too long")
        if label and not re.fullmatch(r"[A-Za-z0-9 _.,/#:()+~'\"-]+", label):
            raise ValueError(f"{key} is invalid")
        sanitized[key] = label

    camera_location_accuracy = (
        str(data.get("camera_location_accuracy") or "").strip().lower()
    )
    if camera_location_accuracy not in {
        "",
        "unknown",
        "exact",
        "approximate",
        "site",
        "region",
        "source",
    }:
        raise ValueError("camera_location_accuracy is invalid")
    sanitized["camera_location_accuracy"] = (
        "" if camera_location_accuracy == "unknown" else camera_location_accuracy
    )
    sanitized["camera_location_private"] = to_bool(
        data.get("camera_location_private", False)
    )

    for key in ("camera_location_evidence", "view_pose_evidence"):
        evidence = str(data.get(key) or "").strip()
        if len(evidence) > 2000:
            raise ValueError(f"{key} is too long")
        sanitized[key] = evidence

    view_description = str(data.get("view_description") or "").strip()
    if len(view_description) > 2000:
        raise ValueError("view_description is too long")
    sanitized["view_description"] = view_description

    view_direction = str(data.get("view_direction") or "").strip()
    if len(view_direction) > 64:
        raise ValueError("view_direction is too long")
    if view_direction and not re.fullmatch(r"[A-Za-z0-9 _./:+-]+", view_direction):
        raise ValueError("view_direction is invalid")
    sanitized["view_direction"] = view_direction

    bearing_value = data.get("view_bearing_degrees")
    if bearing_value in {None, ""}:
        sanitized["view_bearing_degrees"] = None
    else:
        try:
            view_bearing_degrees = float(bearing_value)
        except (TypeError, ValueError):
            raise ValueError("view_bearing_degrees is invalid") from None
        if not 0 <= view_bearing_degrees < 360:
            raise ValueError("view_bearing_degrees is invalid")
        sanitized["view_bearing_degrees"] = view_bearing_degrees

    for key, min_value, max_value, inclusive_min in [
        ("view_pitch_degrees", -90.0, 90.0, True),
        ("view_roll_degrees", -180.0, 180.0, True),
        ("view_horizontal_fov_degrees", 0.0, 360.0, False),
        ("view_vertical_fov_degrees", 0.0, 180.0, False),
    ]:
        raw_value = data.get(key)
        if raw_value in {None, ""}:
            sanitized[key] = None
            continue
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} is invalid") from None
        if inclusive_min:
            valid = min_value <= numeric_value <= max_value
        else:
            valid = min_value < numeric_value <= max_value
        if not valid:
            raise ValueError(f"{key} is invalid")
        sanitized[key] = numeric_value

    view_mount_height = str(data.get("view_mount_height") or "").strip()
    if len(view_mount_height) > 128:
        raise ValueError("view_mount_height is too long")
    if view_mount_height and not re.fullmatch(
        r"[A-Za-z0-9 _./:+~'\"-]+", view_mount_height
    ):
        raise ValueError("view_mount_height is invalid")
    sanitized["view_mount_height"] = view_mount_height

    view_pose_confidence = str(data.get("view_pose_confidence") or "").strip().lower()
    if view_pose_confidence not in {
        "",
        "unknown",
        "estimated",
        "operator",
        "calibrated",
    }:
        raise ValueError("view_pose_confidence is invalid")
    sanitized["view_pose_confidence"] = (
        "" if view_pose_confidence == "unknown" else view_pose_confidence
    )

    view_staticness = str(data.get("view_staticness") or "").strip().lower()
    if view_staticness not in {
        "",
        "unknown",
        "static",
        "slight_drift",
        "drifting",
        "ptz",
        "rotating",
        "composite",
    }:
        raise ValueError("view_staticness is invalid")
    sanitized["view_staticness"] = (
        "" if view_staticness == "unknown" else view_staticness
    )

    view_metadata = str(data.get("view_metadata") or "").strip()
    if len(view_metadata) > 8000:
        raise ValueError("view_metadata is too long")
    if view_metadata:
        try:
            json.loads(view_metadata)
        except Exception:
            raise ValueError("view_metadata must be valid JSON") from None
    sanitized["view_metadata"] = view_metadata

    try:
        view_metadata_version = int(data.get("view_metadata_version", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError("view_metadata_version is invalid") from None
    if view_metadata_version < 0:
        raise ValueError("view_metadata_version is invalid")
    sanitized["view_metadata_version"] = view_metadata_version

    view_metadata_history = str(data.get("view_metadata_history") or "").strip()
    if len(view_metadata_history) > 50000:
        raise ValueError("view_metadata_history is too long")
    if view_metadata_history:
        try:
            json.loads(view_metadata_history)
        except Exception:
            raise ValueError("view_metadata_history must be valid JSON") from None
    sanitized["view_metadata_history"] = view_metadata_history

    for key in [
        "notes",
        "popup_xpath",
        "dedicated_xpath",
        "callback_url",
        "proxy",
        "groups",
        "object_filter",
        "auth_username",
        "auth_password",
    ]:
        value = data.get(key)
        if key == "proxy":
            value = validate_proxy(value)
        if value not in [None, ""]:
            sanitized[key] = value

    # Boolean flags are already converted by the route but we handle them
    # here as a fallback for direct API use.
    def _to_bool(value: object) -> bool:
        return to_bool(value)

    for key in [
        "invert",
        "dark",
        "disable_autocrop",
        "headless",
        "stealth",
        "browser",
        "livecaption",
        "danger",
    ]:
        sanitized[key] = _to_bool(data.get(key, False))

    return sanitized


MAX_WORKERS_MAX = max(1, (os.cpu_count() or 1) * 2)

INTEGER_RANGES = {
    "PORT": (1024, 65535),
    "HTTPS_PORT": (1, 65535),
    "EMAIL_SMTP_PORT": (1, 65535),
    "MAX_WORKERS": (1, MAX_WORKERS_MAX),
    "FFMPEG_THREADS": (1, None),
    "NUM_FRAMES": (1, None),
    "CAPTURE_TIMEOUT": (1, None),
    "LIVE_FALLBACK_FPS": (1, None),
    "LIVE_MAX_FAILURES": (1, None),
    "CHYRON_SPEED": (0, None),
    "WATCHDOG_FAILURE_THRESHOLD": (1, None),
    "WATCHDOG_RESTART_COOLDOWN": (1, None),
    "WATCHDOG_MAX_FILE_HANDLES": (1, None),
    "CRAWLER_STARTUP_SPREAD": (0, None),
    "SESSION_TIMEOUT_MINUTES": (1, None),
}

BOOLEAN_SETTINGS = {
    "DEBUG",
    "DEBUG_MODE",
    "LOW_CPU_MODE",
    "HTTPS_ENABLED",
    "HTTPS_ONLY",
    "HTTPS_SELF_SIGNED",
    "SESSION_COOKIE_SECURE",
    "SESSION_COOKIE_HTTPONLY",
    "CLOCK_OVERLAY",
    "CLOCK_DIGITAL",
    "CLOCK_NAVBAR",
    "HEALTH_STATUS_ALWAYS_VISIBLE",
    "DISCOVERY_AUTOSTART",
    "EMAIL_ENABLED",
    "EMAIL_USE_TLS",
    "SMS_ENABLED",
    "CAP_ENABLED",
    "ENFORCE_DOMAIN_IN_HOST",
    "FFMPEG_HWACCEL",
    "NOTIFY_ON_MOTION",
    "NOTIFY_ON_CAPTION",
    "ALLOW_PRIVATE_CALLBACK_URLS",
}


def validate_setting(name: str, value: str) -> str | None:
    """Return sanitized ``value`` for the given setting ``name``.

    Unknown setting names are returned unchanged. Numeric settings are
    validated against predefined ranges. Boolean settings normalize any
    truthy value to ``"True"`` and everything else to ``"False"``.
    ``None`` is returned when validation fails.
    """

    if value is None:
        return None

    key = str(name or "").upper()
    val = str(value).strip()

    if key == "TZ":
        try:
            ZoneInfo(val)
            return val
        except Exception:
            return None

    if key in {"LOG_LEVEL", "FLASK_LOG_LEVEL"}:
        level = val.upper()
        if level in {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}:
            return level
        return None

    if key == "VISUAL_TIMESTAMP_MODE":
        mode = val.lower()
        if mode in {"clean", "compact", "debug", "off", "full"}:
            return "clean" if mode == "off" else ("debug" if mode == "full" else mode)
        return None

    if key == "FFMPEG_HWACCEL":
        return "auto" if to_bool(val) or val.lower() == "auto" else "False"

    if key in BOOLEAN_SETTINGS:
        return "True" if to_bool(val) else "False"

    if key in INTEGER_RANGES:
        try:
            ivalue = int(val)
        except (TypeError, ValueError):
            return None
        min_val, max_val = INTEGER_RANGES[key]
        if min_val is not None and ivalue < min_val:
            return None
        if max_val is not None and ivalue > max_val:
            return None
        if key == "PORT":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(("0.0.0.0", ivalue))
            except OSError:
                return None
            finally:
                sock.close()
        return str(ivalue)

    email_re = r"^[^@\s]+@[^@.\s]+(?:\.[^@.\s]+)+$"

    if key in {"EMAIL_SENDER", "CAP_SENDER"}:
        if not val:
            return ""
        return val if re.fullmatch(email_re, val) else None

    if key == "EMAIL_RECIPIENTS":
        if not val:
            return ""
        addrs = [a.strip() for a in val.split(";") if a.strip()]
        if not addrs:
            addrs = [a.strip() for a in val.split(",") if a.strip()]
        if all(re.fullmatch(email_re, a) for a in addrs):
            return ",".join(addrs)
        return None

    if key == "CAP_ENDPOINT":
        return validate_url(val) or ""

    return val


def url_matches_host(url: str, domain: str) -> bool:
    """Match an exact DNS hostname or its subdomains, never URL text."""
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)
