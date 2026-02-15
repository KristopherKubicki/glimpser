from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

HOST_CAPS_PATH = os.getenv("LIVE_HOST_CAPS_PATH", "data/live_host_caps.json")
PERSIST_EVERY_SECONDS = float(os.getenv("LIVE_HOST_CAPS_PERSIST_EVERY", "5"))


@dataclass
class HostCaps:
    last_ok_ts: float = 0.0
    last_fail_ts: float = 0.0
    ok_count: int = 0
    fail_count: int = 0
    avoid_until_ts: float = 0.0


_lock = threading.Lock()
_caps: dict[str, dict[str, Any]] = {}
_last_persist = 0.0
_loaded = False


def _now() -> float:
    return time.time()


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(HOST_CAPS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _caps.update(data)
    except FileNotFoundError:
        return
    except Exception:
        return


def _persist(force: bool = False) -> None:
    global _last_persist
    now = _now()
    if not force and now - _last_persist < PERSIST_EVERY_SECONDS:
        return
    _last_persist = now
    os.makedirs(os.path.dirname(HOST_CAPS_PATH) or ".", exist_ok=True)
    tmp = HOST_CAPS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_caps, f, indent=2, sort_keys=True)
    os.replace(tmp, HOST_CAPS_PATH)


def get(host_key: str) -> HostCaps:
    k = str(host_key or "").strip()
    if not k:
        return HostCaps()
    with _lock:
        _load()
        raw = _caps.get(k) or {}
        if not isinstance(raw, dict):
            raw = {}
        c = HostCaps()
        for field in c.__dict__.keys():
            if field in raw:
                setattr(c, field, raw.get(field))
        c.last_ok_ts = float(c.last_ok_ts or 0)
        c.last_fail_ts = float(c.last_fail_ts or 0)
        c.ok_count = int(c.ok_count or 0)
        c.fail_count = int(c.fail_count or 0)
        c.avoid_until_ts = float(c.avoid_until_ts or 0)
        return c


def should_attempt(host_key: str) -> bool:
    c = get(host_key)
    return _now() >= float(c.avoid_until_ts or 0)


def record_success(host_key: str) -> None:
    k = str(host_key or "").strip()
    if not k:
        return
    with _lock:
        _load()
        c = get(k)
        c.last_ok_ts = _now()
        c.ok_count += 1
        c.fail_count = 0
        c.avoid_until_ts = 0.0
        _caps[k] = c.__dict__.copy()
        _persist()


def record_failure(host_key: str, *, reason: str = "") -> None:
    k = str(host_key or "").strip()
    if not k:
        return
    with _lock:
        _load()
        c = get(k)
        now = _now()
        c.last_fail_ts = now
        c.fail_count += 1

        # Circuit breaker:
        # - after a few quick failures, back off briefly to avoid stampeding a
        #   degraded host (bad LAN day, camera rebooting, etc.).
        recent_fail_window_s = 30
        if (c.last_ok_ts or 0) < now - recent_fail_window_s and c.fail_count >= 3:
            # Back off longer when it's clearly not recovering.
            c.avoid_until_ts = now + 60
        elif c.fail_count >= 3:
            c.avoid_until_ts = max(float(c.avoid_until_ts or 0), now + 20)

        _caps[k] = c.__dict__.copy()
        _persist()
