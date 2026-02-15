from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

CAPS_PATH = os.getenv("LIVE_CAPS_PATH", "data/live_caps.json")
PERSIST_EVERY_SECONDS = float(os.getenv("LIVE_CAPS_PERSIST_EVERY", "5"))


@dataclass
class LiveCaps:
    kind: str = "unknown"  # rtsp|hls|mjpeg|snapshot|web|unknown
    last_ok_ts: float = 0.0
    last_fail_ts: float = 0.0
    ok_count: int = 0
    fail_count: int = 0
    last_ttfb_ms: int = 0
    avg_ttfb_ms: int = 0
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
        with open(CAPS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _caps.update(data)
    except FileNotFoundError:
        return
    except Exception:
        # Best-effort cache; ignore corruption.
        return


def _persist(force: bool = False) -> None:
    global _last_persist
    now = _now()
    if not force and now - _last_persist < PERSIST_EVERY_SECONDS:
        return
    _last_persist = now
    os.makedirs(os.path.dirname(CAPS_PATH) or ".", exist_ok=True)
    tmp = CAPS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_caps, f, indent=2, sort_keys=True)
    os.replace(tmp, CAPS_PATH)


def guess_kind(url: str) -> str:
    u = (url or "").strip()
    lower = u.lower()
    if lower.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if any(ext in lower for ext in (".m3u8",)):
        return "hls"
    if any(ext in lower for ext in (".mjpg", ".mjpeg")):
        return "mjpeg"
    if lower.endswith((".jpg", ".jpeg", ".png")) or "/picture" in lower:
        return "snapshot"
    try:
        parsed = urlparse(u)
    except Exception:
        return "unknown"
    if parsed.scheme in {"http", "https"}:
        return "web"
    return "unknown"


def get(url: str) -> LiveCaps:
    if not url:
        return LiveCaps()
    with _lock:
        _load()
        raw = _caps.get(url) or {}
        if not isinstance(raw, dict):
            raw = {}
        c = LiveCaps()
        for k in c.__dict__.keys():
            if k in raw:
                setattr(c, k, raw.get(k))
        # Coerce types
        c.kind = str(c.kind or "unknown")
        c.last_ok_ts = float(c.last_ok_ts or 0)
        c.last_fail_ts = float(c.last_fail_ts or 0)
        c.ok_count = int(c.ok_count or 0)
        c.fail_count = int(c.fail_count or 0)
        c.last_ttfb_ms = int(c.last_ttfb_ms or 0)
        c.avg_ttfb_ms = int(c.avg_ttfb_ms or 0)
        c.avoid_until_ts = float(c.avoid_until_ts or 0)
        if c.kind == "unknown":
            c.kind = guess_kind(url)
        return c


def should_attempt_live(url: str) -> bool:
    c = get(url)
    if c.kind not in {"rtsp", "hls", "mjpeg"}:
        return False
    return _now() >= float(c.avoid_until_ts or 0)


def record_success(url: str, *, ttfb_ms: int | None = None) -> None:
    if not url:
        return
    with _lock:
        _load()
        raw = _caps.get(url)
        if not isinstance(raw, dict):
            raw = {}
        c = get(url)
        c.last_ok_ts = _now()
        c.ok_count += 1
        c.fail_count = 0
        c.avoid_until_ts = 0.0
        if ttfb_ms is not None:
            t = max(0, int(ttfb_ms))
            c.last_ttfb_ms = t
            if c.avg_ttfb_ms:
                # Simple EMA-ish average.
                c.avg_ttfb_ms = int((c.avg_ttfb_ms * 0.7) + (t * 0.3))
            else:
                c.avg_ttfb_ms = t
        _caps[url] = c.__dict__.copy()
        _persist()


def record_failure(url: str, *, reason: str = "") -> None:
    if not url:
        return
    with _lock:
        _load()
        c = get(url)
        c.last_fail_ts = _now()
        c.fail_count += 1
        # If we're repeatedly failing to produce bytes, back off to avoid hammering
        # the camera (or a snapshot endpoint that isn't really a stream).
        if (
            reason == "no_output"
            and c.fail_count >= 3
            and (c.last_ok_ts or 0) < _now() - 60
        ):
            c.avoid_until_ts = _now() + 120
        _caps[url] = c.__dict__.copy()
        _persist()
