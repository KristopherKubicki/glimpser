# app/utils/validators.py

from werkzeug.utils import secure_filename
import re


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

    url = (data.get("url") or "").strip()
    if not url:
        raise ValueError("url is required")
    sanitized["url"] = url

    try:
        frequency = int(data.get("frequency", 30) or 30)
    except (TypeError, ValueError):
        frequency = 30
    if frequency < 1:
        frequency = 1
    if frequency > 525600:
        frequency = 525600
    sanitized["frequency"] = frequency

    try:
        timeout = int(data.get("timeout", 10) or 10)
    except (TypeError, ValueError):
        timeout = 10
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
