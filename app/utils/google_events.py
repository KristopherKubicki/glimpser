"""Durable, bounded Google camera events, separate from capture timestamps."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

EVENT_KINDS = {
    "sdm.devices.events.DoorbellChime.Chime": ("doorbell", 500),
    "sdm.devices.events.CameraPerson.Person": ("person", 450),
    "sdm.devices.events.CameraMotion.Motion": ("motion", 300),
}
MAX_AGE_SECONDS = 120


def event_database() -> Path:
    """Keep event state beside the application database, outside web assets."""
    from app.config import DATABASE_PATH

    return Path(DATABASE_PATH).with_name("google_events.sqlite3")


def normalize_event(payload: dict, cameras: dict[str, str], now: float) -> dict | None:
    """Accept recent camera activity from explicitly mapped SDM resources only."""
    if not isinstance(payload, dict) or payload.get("eventThreadState") == "ENDED":
        return None
    update = payload.get("resourceUpdate")
    if not isinstance(update, dict):
        return None
    resource = update.get("name")
    camera = cameras.get(resource) if isinstance(resource, str) else None
    events = update.get("events")
    event_id = payload.get("eventId")
    if not camera or not isinstance(events, dict):
        return None
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 256:
        return None
    try:
        stamp = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        occurred = stamp.timestamp()
    except (KeyError, ValueError, OverflowError):
        return None
    if not 0 <= now - occurred <= MAX_AGE_SECONDS:
        return None
    kinds = [value for key, value in EVENT_KINDS.items() if key in events]
    if not kinds:
        return None
    kind, score = max(kinds, key=lambda item: item[1])
    thread = payload.get("eventThreadId")
    if not isinstance(thread, str) or not 1 <= len(thread) <= 256:
        thread = event_id
    return {
        "event_id": event_id,
        "thread_id": thread,
        "camera": camera,
        "kind": kind,
        "score": score,
        "occurred": occurred,
        "received": now,
    }


class EventStore:
    """Persist deduplication before Pub/Sub acknowledgement; retain one day."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id TEXT, thread_id TEXT, camera TEXT, kind TEXT,
                score INTEGER, occurred REAL, received REAL,
                PRIMARY KEY(camera, event_id))""")
            db.execute(
                "CREATE TABLE IF NOT EXISTS health (name TEXT PRIMARY KEY, value TEXT)"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Return a short-lived connection with a bounded lock wait."""
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(
        self, payload: dict, cameras: dict[str, str], now: float | None = None
    ) -> bool:
        """Store accepted activity once; never rewrite a camera capture time."""
        now = time.time() if now is None else now
        event = normalize_event(payload, cameras, now)
        with self.connect() as db:
            db.execute("DELETE FROM events WHERE received < ?", (now - 86400,))
            if event is None:
                return False
            result = db.execute(
                "INSERT OR IGNORE INTO events VALUES (:event_id,:thread_id,:camera,:kind,:score,:occurred,:received)",
                event,
            )
            return result.rowcount == 1

    def health(
        self,
        name: str,
        status: str,
        now: float | None = None,
        *,
        counters: dict | None = None,
    ) -> None:
        """Persist only sanitized subscriber state, never credentials/payloads."""
        value = {"status": status, "checked_at": time.time() if now is None else now}
        # Explicit numeric allowlist prevents raw payloads or credentials entering health.
        for key in (
            "started_at",
            "received",
            "accepted",
            "last_message_at",
            "last_accepted_at",
        ):
            metric = (counters or {}).get(key)
            if isinstance(metric, (int, float)) and not isinstance(metric, bool):
                value[key] = metric
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO health VALUES (?,?)", (name, json.dumps(value))
            )

    def landing_events(
        self, scenes: list[dict], now: float | None = None
    ) -> list[dict]:
        """Project fresh events only for priority cameras allowed in this view."""
        now = time.time() if now is None else now
        allowed = {
            scene["hero"]["name"]: scene
            for scene in scenes
            if scene.get("hero", {}).get("priority_event")
        }
        with self.connect() as db:
            rows = db.execute(
                "SELECT camera,thread_id,kind,score,occurred FROM events "
                "WHERE occurred BETWEEN ? AND ? ORDER BY occurred DESC,score DESC",
                (now - MAX_AGE_SECONDS, now),
            ).fetchall()
        result, seen = [], set()
        for camera, thread, kind, score, occurred in rows:
            if camera not in allowed or camera in seen:
                continue
            seen.add(camera)
            result.append(
                {
                    "camera_name": camera,
                    "key": f"google:{camera}:{thread}",
                    "kind": kind,
                    "source": "google-event",
                    "priority": True,
                    "interrupt_ms": 30000,
                    "replay_available": False,
                    "occurred_at": datetime.fromtimestamp(
                        occurred, timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "level": "significant" if score >= 450 else "alert",
                    "motion_score": score,
                    "prefer_video": False,
                    "scene_id": allowed[camera]["id"],
                }
            )
        return result


def landing_events(scenes: list[dict]) -> list[dict]:
    """Read subscriber events if provisioned; otherwise leave rotation alone."""
    path = event_database()
    if not path.exists():
        return []
    # A busy/unavailable optional event store must not break kiosk metadata.
    try:
        return EventStore(path).landing_events(scenes)
    except (sqlite3.Error, OSError):
        return []
