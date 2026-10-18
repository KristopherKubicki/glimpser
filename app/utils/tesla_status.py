"""Passive Tesla capture health. Image retrieval is not vehicle telemetry."""

import json
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

STATE = Path.home() / ".local/share/tesla-ingest"
HEALTH = Path.home() / ".local/state/glimpser/tesla-health.json"
FEEDS = {name: 16200 for name in ("Front", "Left", "Right", "Rear")}
FEEDS.update(App=2700, Map=2700)


def stamp(value):
    """Read UTC database or offset-bearing worker timestamps."""
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (
            date.replace(tzinfo=timezone.utc).timestamp()
            if not date.tzinfo
            else date.timestamp()
        )
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def read_json(path):
    """Treat missing or malformed state as unknown, without exposing exceptions."""
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def project(timestamps, workers, schedules, now):
    """Separate published-image freshness from worker and schedule health."""
    feeds = []
    for suffix, limit in FEEDS.items():
        at = stamp(timestamps.get("Tesla-" + suffix))
        age = now - at if at is not None else None
        feeds.append(
            {
                "name": "Tesla-" + suffix,
                "state": "fresh"
                if age is not None and -5 <= age <= limit
                else "stale"
                if age is not None and age >= 0
                else "unknown",
                "captured_at": at,
                "age_seconds": int(max(0, age))
                if age is not None and age >= -5
                else None,
            }
        )
    result = {"checked_at": now, "feeds": feeds, "workers": {}}
    for kind, limit in (("live", 16200), ("app", 2700)):
        worker = workers.get(kind, {})
        at = stamp(worker.get("checked_at"))
        state = worker.get("state")
        state = state if state in ("ok", "failed", "skipped") else "unknown"
        if at is None or not -5 <= now - at <= limit:
            state = "unknown"
        if state == "unknown":
            worker = {}  # Expired reports cannot establish the current failure reason.
        result["workers"][kind] = {
            "state": state,
            "reason": "sentry_off"
            if "Sentry Mode is off" in str(worker.get("reason", ""))
            else "budget"
            if "budget exhausted" in str(worker.get("reason", ""))
            else "capture_failed"
            if worker.get("state") == "failed"
            else "",
            "checked_at": at,
            "schedule": schedules.get(kind, "unknown")
            if schedules.get(kind) in ("active", "inactive", "failed")
            else "unknown",
        }
    result["fresh_cameras"] = sum(row["state"] == "fresh" for row in feeds[:4])
    result["state"] = (
        "ok"
        if result["fresh_cameras"] == 4
        and result["workers"]["live"]["state"] == "ok"
        and result["workers"]["live"]["schedule"] == "active"
        else "degraded"
    )
    return result


def published_stamp(directory, name):
    """Use the image filename, not the later database write time, for pinning."""
    dates = []
    pattern = re.compile(re.escape(name) + r"_(\d{14})(?:_blank)?\.png$")
    try:
        for image in directory.glob("*.png"):
            match = pattern.fullmatch(image.resolve().name)
            if match and image.stat().st_size:
                try:
                    dates.append(datetime.strptime(match[1], "%Y%m%d%H%M%S"))
                except ValueError:
                    continue
    except OSError:
        return None
    return max(dates).isoformat() if dates else None


def collect(database, schedules, now=None, state=STATE):
    """Read only the six configured feed timestamps and capture receipts."""
    now = time.time() if now is None else now
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2) as db:
        timestamps = dict(
            db.execute(
                "SELECT name,last_screenshot_time FROM templates WHERE name IN (?,?,?,?,?,?)",
                tuple("Tesla-" + suffix for suffix in FEEDS),
            )
        )
    # Upload processing can cross a second boundary before writing the DB row.
    # Only canonical image times are valid for the timestamp-pinned image endpoint.
    for name in timestamps:
        timestamps[name] = published_stamp(
            Path(database).parent / "screenshots" / name, name
        )
    return project(
        timestamps,
        {kind: read_json(state / f"{kind}-status.json") for kind in ("live", "app")},
        schedules,
        now,
    )


def snapshot(now=None):
    """Expire the independent collector heartbeat even when old images exist."""
    now = time.time() if now is None else now
    data = read_json(HEALTH)
    at = data.get("checked_at")
    if (
        isinstance(at, bool)
        or not isinstance(at, (int, float))
        or not math.isfinite(at)
        or not -5 <= now - at <= 300
    ):
        return {"state": "unknown", "checked_at": None, "feeds": [], "workers": {}}
    return data
