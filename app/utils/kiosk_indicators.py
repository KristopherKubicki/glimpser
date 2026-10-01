"""Bounded, authenticated indicator events shared with Hubitat's chime handler."""

import hmac
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from urllib.request import urlopen

TOKEN = Path.home() / ".config/glimpser/kiosk-indicators.token"
STATE = Path.home() / ".local/state/glimpser/kiosk-indicators.json"
_LOCK = threading.RLock()
_PRIVACY = {"checked": 0.0, "value": "unknown"}
KINDS = {"door", "person", "package", "sms", "heartbeat"}
PRIVACY_URL = os.environ.get("GLIMPSER_PRIVACY_GUARD_URL", "").strip()


def authenticated(header: str) -> bool:
    """Require the dedicated producer credential, never a browser session."""
    try:
        token = TOKEN.read_text().strip()
        return bool(token) and hmac.compare_digest(
            header.encode(), ("Bearer " + token).encode()
        )
    except OSError:
        return False


def _read() -> dict:
    try:
        value = json.loads(STATE.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def accept(value: object, now: float) -> None:
    """Persist fresh allowlisted signals; message bodies are never accepted."""
    if not isinstance(value, dict) or set(value) - {"id", "kind", "at", "label"}:
        raise ValueError("invalid event")
    kind, identity = value.get("kind"), value.get("id")
    if (
        kind not in KINDS
        or not isinstance(identity, str)
        or not re.fullmatch(r"[A-Za-z0-9:_-]{1,120}", identity)
    ):
        raise ValueError("invalid event")
    at = float(value.get("at", 0)) / 1000
    if not math.isfinite(at) or not -5 <= now - at <= 15:
        raise ValueError("expired event")
    label = value.get("label", "")
    if not isinstance(label, str) or len(label) > 100:
        raise ValueError("invalid label")
    event = {"id": identity, "kind": kind, "at": at}
    if kind == "door":
        event["label"] = label
    with _LOCK:
        state = _read()
        events = [e for e in state.get("events", []) if now - e["at"] < 60]
        if kind != "heartbeat" and not any(e["id"] == identity for e in events):
            events.append(event)
        state = {
            "events": events[-32:],
            "producer_at": max(at, state.get("producer_at", 0)),
        }
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(state, handle)
        os.replace(temporary, STATE)


def privacy(now: float) -> str:
    """Return explicit fresh privacy status; errors and silence mean unknown."""
    if not PRIVACY_URL:
        return "unknown"
    with _LOCK:
        if now - _PRIVACY["checked"] < 2:
            return _PRIVACY["value"]
        result = "unknown"
        try:
            with urlopen(PRIVACY_URL, timeout=1) as response:
                data = json.load(response)
            age = now - float(data.get("updated_ts", 0))
            if (
                data.get("available") is True
                and -5 <= age <= 120
                and isinstance(data.get("active"), bool)
            ):
                result = "active" if data["active"] else "inactive"
        except (OSError, ValueError, TypeError):
            pass
        _PRIVACY.update(checked=now, value=result)
        return result


def snapshot(profile: str, now: float | None = None) -> dict:
    """Expose only recent event labels and status, scoped to the room profile."""
    now = time.time() if now is None else now
    with _LOCK:
        state = _read()
    age = now - state.get("producer_at", 0)
    value = {
        "server_time": now,
        "available": -5 <= age <= 90,
        "events": [e for e in state.get("events", []) if -5 <= now - e["at"] <= 10],
    }
    if profile == "office":
        value["privacy"] = privacy(now)
    return value
