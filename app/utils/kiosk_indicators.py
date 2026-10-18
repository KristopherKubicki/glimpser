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

from app.status_config import STATUS_CONFIG

TOKEN = Path.home() / ".config/glimpser/kiosk-indicators.token"
STATE = Path.home() / ".local/state/glimpser/kiosk-indicators.json"
_LOCK = threading.RLock()
_PRIVACY = {"checked": 0.0, "value": "unknown"}
KINDS = {"door", "person", "package", "sms", "heartbeat"}
PRIVACY_URL = os.environ.get(
    "GLIMPSER_PRIVACY_GUARD_URL", STATUS_CONFIG.get("privacy_url", "")
).strip()


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


def _status(value: object, now: float) -> dict:
    """Validate the compact office snapshot without accepting arbitrary host data."""
    if not isinstance(value, dict) or set(value) != {
        "hal",
        "garage",
        "cue",
        "phase",
        "quiet",
    }:
        raise ValueError("invalid status")
    if value["phase"] not in {"day", "evening", "night"} or not isinstance(
        value["quiet"], bool
    ):
        raise ValueError("invalid phase")
    hal, garage, cue = value["hal"], value["garage"], value["cue"]
    if not isinstance(hal, dict) or set(hal) != {
        "level",
        "reason",
        "updated",
        "since",
        "metrics",
    }:
        raise ValueError("invalid HAL status")
    if hal["level"] not in {
        "disabled",
        "starting",
        "normal",
        "yellow",
        "red",
        "unknown",
    }:
        raise ValueError("invalid HAL level")
    if not isinstance(hal["reason"], str) or len(hal["reason"]) > 160:
        raise ValueError("invalid HAL reason")
    if not isinstance(garage, dict) or set(garage) != {"open", "since"}:
        raise ValueError("invalid garage status")
    if garage["open"] is not None and not isinstance(garage["open"], bool):
        raise ValueError("invalid contact")
    if not isinstance(cue, dict) or set(cue) != {"kind", "at", "until"}:
        raise ValueError("invalid cue")
    kinds = {
        "",
        "main",
        "upstairs",
        "basement",
        "office",
        "approach",
        "depart",
        "hour",
        "mode",
        "settle",
        "garage-open",
        "garage-close",
        "hal-yellow",
        "hal-red",
        "hal-clear",
        "hal-unknown",
    }
    kinds |= {
        f"{prefix}-{key}"
        for prefix in ("open", "entry")
        for key in ("393", "394", "395", "396", "392", "401", "405")
    }
    if cue["kind"] not in kinds:
        raise ValueError("invalid cue kind")
    result = json.loads(json.dumps(value))
    for group, keys in (
        ("hal", ("updated", "since")),
        ("garage", ("since",)),
        ("cue", ("at", "until")),
    ):
        for key in keys:
            raw = result[group][key]
            if (
                isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(raw)
            ):
                raise ValueError("invalid status time")
            stamp = raw / 1000
            if stamp < 0 or stamp > now + (60 if key == "until" else 5):
                raise ValueError("invalid status time")
            result[group][key] = stamp
    metrics = hal["metrics"]
    bounds = {"cpu": 100, "memory": 100, "temperature": 150, "freeGB": 1000000}
    if not isinstance(metrics, dict) or set(metrics) - bounds.keys():
        raise ValueError("invalid metrics")
    for key, number in metrics.items():
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or not 0 <= number <= bounds[key]
        ):
            raise ValueError("invalid metric")
    return result


def accept(value: object, now: float) -> None:
    """Persist fresh allowlisted signals; message bodies are never accepted."""
    if not isinstance(value, dict) or set(value) - {
        "id",
        "kind",
        "at",
        "label",
        "status",
    }:
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
    status = None
    if "status" in value:
        if kind != "heartbeat":
            raise ValueError("status requires heartbeat")
        status = _status(value["status"], now)
    event = {"id": identity, "kind": kind, "at": at}
    if kind == "door":
        event["label"] = label
    with _LOCK:
        state = _read()
        events = [e for e in state.get("events", []) if now - e["at"] < 60]
        if kind != "heartbeat" and not any(e["id"] == identity for e in events):
            events.append(event)
        if status is not None and at >= state.get("status_at", 0):
            state.update(status=status, status_at=at)
        state.update(
            events=events[-32:], producer_at=max(at, state.get("producer_at", 0))
        )
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
    if profile in {"office", "living"} and (
        os.getenv("GLIMPSER_KIOSK_EXTENDED_STATUS") == "1"
        or STATUS_CONFIG.get("extended_kiosk", False)
    ):
        from app.utils.perimeter_status import snapshot as perimeter_snapshot
        from app.utils.tesla_status import snapshot as tesla_snapshot

        value["perimeter"] = perimeter_snapshot(now)
        value["tesla"] = tesla_snapshot(now)
    if profile == "office":
        value["privacy"] = privacy(now)
        status_age = now - state.get("status_at", 0)
        if (
            value["available"]
            and -5 <= status_age <= 90
            and isinstance(state.get("status"), dict)
        ):
            value["status"] = state["status"]
    return value
