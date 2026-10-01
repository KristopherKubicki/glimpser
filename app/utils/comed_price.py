from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

COMED_FEED_URL = "https://hourlypricing.comed.com/rrtp/ServletFeed"
COMED_REFERER = "https://hourlypricing.comed.com/live-prices/"
COMED_TIMEZONE = "America/Chicago"
DEFAULT_TIMEOUT_SECONDS = 8

_DATE_UTC_POINT_RE = re.compile(
    r"\[\s*Date\.UTC\(\s*"
    r"(?P<year>\d{4})\s*,\s*"
    r"(?P<month>\d{1,2})\s*,\s*"
    r"(?P<day>\d{1,2})\s*,\s*"
    r"(?P<hour>\d{1,2})\s*,\s*"
    r"(?P<minute>\d{1,2})\s*,\s*"
    r"(?P<second>\d{1,2})\s*\)\s*,\s*"
    r"(?P<value>-?\d+(?:\.\d+)?|null)\s*\]",
    re.IGNORECASE,
)


def _market_now(now: datetime | None = None) -> datetime:
    zone = ZoneInfo(COMED_TIMEZONE)
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(zone)


def _format_feed_date(value: datetime) -> str:
    return value.strftime("%Y%m%d")


def _read_url(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/javascript,*/*;q=0.8",
            "Referer": COMED_REFERER,
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _feed_url(feed_type: str, **params: str) -> str:
    query = {"type": feed_type, **{k: v for k, v in params.items() if v}}
    return f"{COMED_FEED_URL}?{urlencode(query)}"


def _fetch_text(
    feed_type: str,
    *,
    fetcher=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    **params: str,
) -> str:
    reader = fetcher or _read_url
    return reader(_feed_url(feed_type, **params), timeout=timeout)


def parse_date_utc_series(payload: str | None) -> list[dict[str, Any]]:
    """Parse ComEd's JavaScript ``Date.UTC`` series into JSON-safe points."""

    points: list[dict[str, Any]] = []
    if not payload:
        return points

    for match in _DATE_UTC_POINT_RE.finditer(payload):
        month = int(match.group("month")) + 1
        value_text = match.group("value").lower()
        value = None if value_text == "null" else float(value_text)
        timestamp = datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
            tzinfo=timezone.utc,
        )
        points.append(
            {
                "iso": timestamp.isoformat().replace("+00:00", "Z"),
                "hour": int(match.group("hour")),
                "minute": int(match.group("minute")),
                "value": value,
            }
        )
    return points


def _fetch_series(
    feed_type: str,
    *,
    date_value: str,
    fetcher=None,
    warnings: list[str],
) -> list[dict[str, Any]]:
    try:
        return parse_date_utc_series(
            _fetch_text(feed_type, fetcher=fetcher, date=date_value)
        )
    except Exception as exc:
        warnings.append(f"{feed_type}:{date_value}: {type(exc).__name__}")
        return []


def _fetch_current_price(
    fetcher=None, warnings: list[str] | None = None
) -> float | None:
    try:
        raw = _fetch_text("instantnumber", fetcher=fetcher)
        data = json.loads(raw)
        value = data.get("avgNum")
        return None if value in (None, "") else float(value)
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"instantnumber: {type(exc).__name__}")
        return None


def _fetch_interval_label(fetcher=None, warnings: list[str] | None = None) -> str:
    try:
        raw = _fetch_text("currentHourlyInterval", fetcher=fetcher)
        return raw.strip().strip('"')
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"currentHourlyInterval: {type(exc).__name__}")
        return ""


def fetch_comed_price_payload(
    now: datetime | None = None,
    *,
    fetcher=None,
) -> dict[str, Any]:
    """Return ComEd hourly-pricing data shaped for the local dark wall view."""

    market_now = _market_now(now)
    market_date = _format_feed_date(market_now)
    previous_date = _format_feed_date(market_now - timedelta(days=1))
    month_date = market_now.strftime("%Y%m")
    warnings: list[str] = []

    today_actual = _fetch_series(
        "day", date_value=market_date, fetcher=fetcher, warnings=warnings
    )
    today_day_ahead = _fetch_series(
        "daynexttoday", date_value=market_date, fetcher=fetcher, warnings=warnings
    )
    previous_actual = _fetch_series(
        "day", date_value=previous_date, fetcher=fetcher, warnings=warnings
    )
    month_average = _fetch_series(
        "month", date_value=month_date, fetcher=fetcher, warnings=warnings
    )

    display_actual = today_actual or previous_actual
    actual_label = "settled today" if today_actual else "previous settled day"
    if not today_actual and previous_actual:
        warnings.append("today-settled-feed-empty")

    return {
        "ok": bool(today_actual or today_day_ahead or previous_actual),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "market_timezone": COMED_TIMEZONE,
        "market_date": market_date,
        "previous_date": previous_date,
        "current_price": _fetch_current_price(fetcher, warnings),
        "current_interval": _fetch_interval_label(fetcher, warnings),
        "actual_label": actual_label,
        "series": {
            "actual": display_actual,
            "today_actual": today_actual,
            "day_ahead": today_day_ahead,
            "previous_actual": previous_actual,
            "month_average": month_average,
        },
        "warnings": warnings,
    }
