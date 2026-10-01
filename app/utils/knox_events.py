"""Read-only Knox camera activity; receipt time is independent of image freshness."""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET

from app.utils.google_events import EventStore, event_database


def configured_cameras() -> dict[str, str]:
    """Load an explicit camera/host allowlist; never discover event sources."""
    try:
        value = json.loads(os.environ.get("GLIMPSER_KNOX_CAMERAS", "{}"))
        if not isinstance(value, dict) or any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(host, str)
            or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host)
            for name, host in value.items()
        ):
            raise ValueError("Invalid camera allowlist")
        return {name: host.lower() for name, host in value.items()}
    except (ValueError, TypeError):
        logging.error("Invalid GLIMPSER_KNOX_CAMERAS; native event sources disabled")
        return {}


CAMERAS = configured_cameras()
END = b"</EventNotificationAlert>"


def frames(chunks):
    """Extract bounded XML records from a multipart camera stream."""
    buffer = b""
    for chunk in chunks:
        buffer += chunk
        while END in buffer:
            end = buffer.index(END) + len(END)
            record, buffer = buffer[:end], buffer[end:]
            start = record.find(b"<EventNotificationAlert")
            if start >= 0 and len(record) <= 65536:
                yield record[start:]
        if len(buffer) > 65536:
            buffer = b""


def motion_state(xml):
    """Return VMD state only; ignore heartbeats, loss alarms, and malformed XML."""
    if len(xml) > 65536 or b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    fields = {node.tag.split("}")[-1]: node.text for node in root}
    if fields.get("eventType") != "VMD" or fields.get("channelID") != "1":
        return None
    state = fields.get("eventState")
    return state if state in {"active", "inactive"} else None


def database():
    """Keep a separate bounded event store beside existing Google event state."""
    return event_database().with_name("knox_events.sqlite3")


def record_motion(store, camera, xml, now=None):
    """Persist native activity once, with a 20-second per-camera burst limit."""
    if camera not in CAMERAS or motion_state(xml) != "active":
        return False
    now = time.time() if now is None else now
    event_id = hashlib.sha256(xml).hexdigest()
    with store.connect() as db:
        db.execute("DELETE FROM events WHERE received < ?", (now - 86400,))
        latest = db.execute(
            "SELECT MAX(received) FROM events WHERE camera=?", (camera,)
        ).fetchone()[0]
        if latest is not None and now - latest < 20:
            return False
        result = db.execute(
            "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?)",
            (event_id, event_id, camera, "motion", 300, now, now),
        )
        return result.rowcount == 1


def landing_events(scenes):
    """Project native events only onto cameras already allowed in this display."""
    path = database()
    if not path.exists():
        return []
    try:
        events = EventStore(path).landing_events(scenes)
    except (OSError, sqlite3.Error):
        return []
    for event in events:
        event["source"] = "knox-camera-event"
        event["key"] = event["key"].replace("google:", "knox:", 1)
    return events
