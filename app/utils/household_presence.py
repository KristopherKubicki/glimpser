"""Durable, conservative household presence; never commands people or devices."""

import json
import logging
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from app import config
from app.utils import hubitat_locations as hub
from app.utils.source_freshness import timestamp

SUBJECT_DETAILS = hub.HOUSEHOLD.get("subjects", {})
SUBJECTS = {key: spec["label"] for key, spec in SUBJECT_DETAILS.items()}
SOURCES = tuple(hub.HOUSEHOLD.get("presence_sources", []))
ARRIVAL_CAMERAS = tuple(hub.HOUSEHOLD.get("arrival_cameras", []))
FRESH_SECONDS = 120
ARRIVAL_SECONDS = 30
DEPARTURE_SECONDS = 300


def _database():
    path = Path(config.DATABASE_PATH).resolve().parent / "household_presence.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS states (subject TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, occurred REAL NOT NULL, payload TEXT NOT NULL)"
    )
    return connection


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


def read_source(spec: dict) -> dict:
    """Read only allowlisted state fields, discarding credentials and preferences."""
    subject, device, label = spec["subject"], spec["device"], spec["label"]
    result = {
        "subject": subject,
        "id": device,
        "label": label,
        "presence": "unknown",
        "available": False,
    }
    if not hub.HUB_URL:
        return result
    try:
        with urlopen(f"{hub.HUB_URL}/device/fullJson/{device}", timeout=3) as response:
            states = json.load(response).get("device", {}).get("currentStates", {})
        state = states.get("presence") or {}
        presence = state.get("value")
        if presence in {"present", "not present"}:
            result.update(
                presence=presence, available=True, changed_at=state.get("date")
            )
        # This network sensor publishes a heartbeat; never trust an old one.
        if spec.get("heartbeat_required"):
            stamp = hub._timestamp((states.get("lastUpdated") or {}).get("date"))
            if (
                not stamp
                or not 0 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 300
            ):
                result.update(presence="unknown", available=False)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


def reconcile(observations: list[dict], now: float | None = None) -> None:
    """Commit debounced transitions and event IDs atomically across processes/restarts.

    Initial observations and recovery after a sampling gap establish a baseline,
    never an arrival. Opposing or missing sources cannot establish departure.
    """
    if not hub.HUB_URL or not SUBJECTS:
        return
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    db = _database()
    try:
        db.execute("BEGIN IMMEDIATE")
        for key, label in SUBJECTS.items():
            row = db.execute(
                "SELECT payload FROM states WHERE subject=?", (key,)
            ).fetchone()
            state = (
                json.loads(row[0])
                if row
                else {"presence": "unknown", "verified": 0, "changed": 0}
            )
            sources = [o for o in observations if o.get("subject") == key]
            valid = [
                o
                for o in sources
                if o.get("available")
                and o.get("presence") in {"present", "not present"}
            ]
            values = {o["presence"] for o in valid}
            complete = bool(sources) and len(valid) == len(sources)
            conflict = len(values) > 1
            # Home evidence can survive one missing source; departure needs every configured source.
            candidate = (
                "present"
                if values == {"present"}
                else "not present" if complete and values == {"not present"} else None
            )
            gap = (
                not state.get("checked")
                or now - state["checked"] > FRESH_SECONDS
                or now < state["checked"]
            )
            state.update(
                checked=now,
                sources=sources,
                conflict=conflict,
                available=bool(valid),
                complete=complete,
            )
            if candidate is None:
                state.pop("pending", None)
                state.pop("pending_since", None)
            elif gap or state["presence"] == "unknown":
                state.update(
                    presence=candidate, verified=now, changed=now, pending=None
                )
            elif candidate == state["presence"]:
                state.update(verified=now, pending=None)
            else:
                if state.get("pending") != candidate:
                    state.update(pending=candidate, pending_since=now)
                delay = ARRIVAL_SECONDS if candidate == "present" else DEPARTURE_SECONDS
                if now - state["pending_since"] >= delay:
                    # Do not interpret recovery from prolonged unknown evidence as a new arrival.
                    recent = now - state.get("verified", 0) <= delay + FRESH_SECONDS
                    state.update(
                        presence=candidate, verified=now, changed=now, pending=None
                    )
                    if recent:
                        event = {
                            "id": str(uuid.uuid4()),
                            "subject_id": f"hubitat-{key}",
                            "label": label,
                            "kind": (
                                "arrival" if candidate == "present" else "departure"
                            ),
                            "occurred_at": _iso(now),
                            "reason": "; ".join(
                                f"{s['label']}: {s['presence']}" for s in valid
                            ),
                        }
                        db.execute(
                            "INSERT INTO events VALUES (?,?,?)",
                            (event["id"], now, json.dumps(event)),
                        )
            db.execute(
                "INSERT OR REPLACE INTO states VALUES (?,?)", (key, json.dumps(state))
            )
        db.execute("DELETE FROM events WHERE occurred < ?", (now - 7 * 86400,))
        db.commit()
    finally:
        db.close()


def poll_presence() -> None:
    """Sample household sensors independently of whether a dashboard is open."""
    if not hub.HUB_URL or not SOURCES:
        return
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            observations = list(pool.map(read_source, SOURCES))
        reconcile(observations)
    except (OSError, sqlite3.Error, ValueError):
        logging.exception(
            "Household presence sampling failed; retaining last confirmed state"
        )


def presence_context(now: float | None = None) -> dict:
    """Return cached state and an auditable event history without network calls."""
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    if not hub.HUB_URL or not SUBJECTS:
        return {"subjects": [], "presence_events": []}
    states, events = {}, []
    db = None
    try:
        db = _database()
        states = {
            key: json.loads(payload)
            for key, payload in db.execute("SELECT subject,payload FROM states")
        }
        events = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM events ORDER BY occurred DESC LIMIT 30"
            )
        ]
    except (OSError, sqlite3.Error, ValueError):
        logging.exception("Presence store unavailable; reporting unknown")
    finally:
        if db is not None:
            db.close()
    subjects = []
    for key, label in SUBJECTS.items():
        state = states.get(key, {})
        verified = state.get("verified", 0)
        stale = not verified or not 0 <= now - verified <= FRESH_SECONDS
        known = state.get("presence", "unknown")
        subjects.append(
            {
                "subject_id": f"hubitat-{key}",
                "label": label,
                "provider": "hubitat",
                "presence": known if not stale else "unknown",
                "last_presence": known,
                "verified_at": _iso(verified),
                "presence_changed_at": _iso(state.get("changed")),
                "stale": stale,
                "conflict": state.get("conflict", False),
                "pending": state.get("pending"),
                "sources": state.get("sources", []),
                "position": None,
                "position_status": "GPS unavailable",
                "location_identity": SUBJECT_DETAILS.get(key, {}).get(
                    "location_identity"
                ),
                "status_note": (
                    "Sources disagree; retaining last confirmed state"
                    if state.get("conflict")
                    else (
                        "Confirming departure"
                        if state.get("pending") == "not present"
                        else (
                            "Confirming arrival"
                            if state.get("pending") == "present"
                            else (
                                "Configured identity; waiting for a live location connection"
                                if SUBJECT_DETAILS.get(key, {}).get("location_identity")
                                and not state.get("sources")
                                else (
                                    "Presence source not connected"
                                    if not state.get("sources")
                                    else (
                                        "Source unavailable; showing last confirmed state"
                                        if not state.get("available")
                                        else "Last reported state verified with Hubitat"
                                    )
                                )
                            )
                        )
                    )
                ),
            }
        )
    return {
        "subjects": subjects,
        "presence_events": [
            event
            for event in events
            if event.get("subject_id") in {f"hubitat-{key}" for key in SUBJECTS}
        ],
    }


def arrival_events(scenes: list[dict], now: float | None = None) -> list[dict]:
    """Expose recent confirmed arrivals only when a recent entrance capture exists."""
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    cameras = []
    for name in ARRIVAL_CAMERAS:
        scene = next((s for s in scenes if s.get("hero", {}).get("name") == name), None)
        if not scene:
            continue
        hero = scene["hero"]
        freshness = hero.get("freshness", {})
        if any(freshness.get(k) for k in ("older", "retained", "clock_ahead")):
            continue
        stamp = timestamp(hero.get("last_screenshot_time"))
        if stamp and 0 <= now - stamp.timestamp() <= 120:
            cameras.append(
                {
                    "name": name,
                    "captured": hero["last_screenshot_time"],
                    "image": f"/clean_screenshot/{name}",
                    "live": f"/live?camera={name}",
                    "freshness": hero.get("freshness", {}),
                    "caption": hero.get("caption", ""),
                }
            )
    if not cameras:
        return []
    result = []
    for event in presence_context(now)["presence_events"]:
        stamp = hub._timestamp(event["occurred_at"])
        if (
            event["kind"] != "arrival"
            or not stamp
            or not 0 <= now - stamp.timestamp() <= 120
        ):
            continue
        result.append(
            {
                "key": "presence:" + event["id"],
                "kind": "arrival",
                "subject_label": event["label"],
                "camera_name": cameras[0]["name"],
                "cameras": cameras,
                "priority": True,
                "level": "alert",
                "interrupt_ms": 26000,
                "occurred_at": event["occurred_at"],
                "reason": event["reason"],
                "replay_available": False,
            }
        )
    return result


def schedule_presence(scheduler) -> None:
    """Tolerate brief scheduler jitter without replaying stale presence polls."""
    if not hub.HUB_URL or not SOURCES:
        return
    scheduler.add_job(
        id="household_presence",
        func=poll_presence,
        trigger="interval",
        seconds=30,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        misfire_grace_time=15,
    )
