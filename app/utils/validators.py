# app/utils/validators.py

from werkzeug.utils import secure_filename
import re
from urllib.parse import urlparse
from ipaddress import ip_address


def is_bool_string(value: object) -> bool:
    """Return ``True`` when ``value`` looks like a boolean string."""

    return str(value).strip().lower() in {
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

    if urlparse(url).scheme not in {"http", "https"}:
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
    return not _is_private_host(host)


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

    url = (data.get("url") or "").strip()
    if not url:
        raise ValueError("url is required")
    sanitized["url"] = url

    try:
        frequency = int(data.get("frequency", default_frequency) or default_frequency)
    except (TypeError, ValueError):
        frequency = default_frequency
    if frequency < 1:
        frequency = 1
    if frequency > 525600:
        frequency = 525600
    sanitized["frequency"] = frequency

    try:
        timeout = int(data.get("timeout", default_timeout) or default_timeout)
    except (TypeError, ValueError):
        timeout = default_timeout
    if timeout < 1:
        timeout = 1
    max_timeout = frequency * 60
    if timeout >= max_timeout:
        timeout = max_timeout - 1
    sanitized["timeout"] = timeout

    try:
        rollback = int(data.get("rollback_frames", 0) or 0)
    except (TypeError, ValueError):
        rollback = 0
    if rollback < 0:
        rollback = 0
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
        return str(value).lower() in {"true", "1", "t", "y", "yes", "on"}

    for key in [
        "invert",
        "dark",
        "headless",
        "stealth",
        "browser",
        "livecaption",
        "danger",
    ]:
        sanitized[key] = _to_bool(data.get(key, False))

    return sanitized


INTEGER_RANGES = {
    "PORT": (1024, 65535),
    "EMAIL_SMTP_PORT": (1, 65535),
    "MAX_WORKERS": (1, None),
    "FFMPEG_THREADS": (1, None),
    "NUM_FRAMES": (1, None),
    "CAPTURE_TIMEOUT": (1, None),
    "LIVE_FALLBACK_FPS": (1, None),
    "LIVE_MAX_FAILURES": (1, None),
    "CHYRON_SPEED": (0, None),
    "WATCHDOG_FAILURE_THRESHOLD": (1, None),
    "WATCHDOG_RESTART_COOLDOWN": (1, None),
    "WATCHDOG_MAX_FILE_HANDLES": (1, None),
    "SESSION_TIMEOUT_MINUTES": (1, None),
}

BOOLEAN_SETTINGS = {
    "DEBUG",
    "DEBUG_MODE",
    "SESSION_COOKIE_SECURE",
    "SESSION_COOKIE_HTTPONLY",
    "CLOCK_OVERLAY",
    "CLOCK_DIGITAL",
    "CLOCK_NAVBAR",
    "HEALTH_STATUS_ALWAYS_VISIBLE",
    "DISCOVERY_AUTOSTART",
    "EMAIL_ENABLED",
    "EMAIL_USE_TLS",
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

    if key in BOOLEAN_SETTINGS:
        return (
            "True" if val.lower() in {"true", "1", "t", "y", "yes", "on"} else "False"
        )

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
        return str(ivalue)

    return val
