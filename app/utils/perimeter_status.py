"""Read-only, allowlisted door/safe coverage; unknown is never an all-clear."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from urllib.request import urlopen

from app.status_config import STATUS_CONFIG

HUB = STATUS_CONFIG.get("hub", "")
# Configured contacts and sensitive-area sensors; no inferred store coverage.
SENSORS = STATUS_CONFIG.get("sensors", [])
_CACHE = {"at": 0.0, "rows": []}
_LOCK = Lock()


def timestamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.timestamp() if stamp.tzinfo else None
    except (TypeError, ValueError, AttributeError, OverflowError):
        return None


def project(spec, device, now):
    identity, label, attribute = spec
    states = device.get("currentStates") or {}
    if not isinstance(states, dict):
        states = {}
    state = states.get(attribute) or {}
    changed = timestamp(state.get("date"))
    # Prefer a device check-in over arbitrary configuration activity. An old
    # contact transition is fine when a recent check-in confirms device health.
    checkin = states.get("lastCheckin") or states.get("lastWakeup")
    reported = (
        timestamp(checkin.get("date"))
        if checkin
        else timestamp(device.get("lastActivityTime") or device.get("lastActivity"))
    )
    if reported is None:
        reported = changed
    fresh = (
        not device.get("disabled")
        and reported is not None
        and -5 <= now - reported <= 86400
    )
    raw = state.get("value")
    allowed = {"open", "closed"} if attribute == "contact" else {"active", "inactive"}
    value = raw if fresh and raw in allowed else "unknown"
    reason = (
        "disabled"
        if device.get("disabled")
        else "missing_report"
        if reported is None
        else "clock_ahead"
        if reported > now + 5
        else "stale_report"
        if now - reported > 86400
        else "invalid_state"
        if raw not in allowed
        else ""
    )
    battery = (states.get("battery") or {}).get("value")
    try:
        low_battery = 0 <= float(battery) <= 20
    except (TypeError, ValueError):
        low_battery = False
    return {
        "id": identity,
        "label": label,
        "attribute": attribute,
        "state": value,
        "reason": reason,
        "last_known": raw if raw in allowed else "unknown",
        "reported_at": reported,
        "changed_at": changed,
        "low_battery": low_battery,
        "open_seconds": max(0, int(now - changed))
        if value == "open" and changed and changed <= now
        else None,
    }


def read(spec, now):
    try:
        with urlopen(f"{HUB}/device/fullJson/{spec[0]}", timeout=1) as response:
            device = json.load(response).get("device", {})
        return project(spec, device, now)
    except (OSError, ValueError, TypeError, AttributeError):
        row = project(spec, {}, now)
        row["reason"] = "read_failed"
        return row


def snapshot(now=None):
    now = time.time() if now is None else now
    with _LOCK:
        if not _CACHE["rows"] or not 0 <= now - _CACHE["at"] < 10:
            with ThreadPoolExecutor(max_workers=10) as pool:
                rows = list(pool.map(lambda spec: read(spec, now), SENSORS))
            _CACHE.update(at=now, rows=rows)
        return {
            "checked_at": _CACHE["at"],
            "site": STATUS_CONFIG.get("site", "Home"),
            "sensors": _CACHE["rows"],
        }
