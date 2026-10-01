"""Conservative presentation checks; these never disable capture or retry jobs."""

import re
from datetime import datetime, timedelta, timezone


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError):
        return None


def landing_feed_issue(details: dict, now: datetime | None = None) -> str:
    """Return a presentation hold reason, or an empty string for usable metadata.

    A quiet camera is not a frozen camera. Do not infer failure merely from a
    lack of motion or identical captions. Existing long-term source checks run
    separately. Page-error classification uses the generated caption headline,
    not operator notes/prompts or incidental errors in a healthy dashboard.
    """
    now = now or datetime.utcnow()
    captured = _timestamp(details.get("last_screenshot_time"))
    if captured is None:
        return "awaiting_capture"
    if captured > now + timedelta(minutes=5):
        return "capture_clock_ahead"
    if details.get("capture_failed"):
        return "capture_failed"
    try:
        frequency = max(1, min(720, int(details.get("frequency") or 30)))
    except (TypeError, ValueError, OverflowError):
        frequency = 30
    # Three scheduled intervals, with slack for transient scheduler/network lag.
    max_age = timedelta(minutes=max(30, frequency * 3))
    if now - captured > max_age:
        return "overdue_capture"
    caption = str(details.get("last_caption") or "").strip().lower()
    headline = caption.split("\t", 1)[0].split("\n", 1)[0]
    if headline == "unreadable":
        headline = caption  # Some captioners put the actual error in the detail.
    if re.search(
        r"(?:captcha.*(?:placeholder|blocking|challenge)|cloudflare.*(?:captcha|challenge)|verify you are human)",
        headline,
    ):
        return "captcha_deferred"
    if re.search(
        r"\b(?:404 page not found|error page|access denied|gateway timeout|product-unavailable error|blank page|blank screen|loading screen|loading placeholder)\b",
        headline,
    ):
        return "unusable_page"
    if re.search(
        r"\b(?:guide data unavailable|no schedule loaded|map tile loading failure|map unavailable)\b",
        headline,
    ):
        return "unusable_page"
    return ""
