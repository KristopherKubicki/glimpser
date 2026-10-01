from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class _Token:
    sem: threading.Semaphore

    def release(self) -> None:
        try:
            self.sem.release()
        except ValueError:
            # Double release shouldn't crash request teardown.
            return


_lock = threading.Lock()
_sems: Dict[Tuple[str, str, int], threading.Semaphore] = {}


def try_acquire(
    host_key: str, *, kind: str, limit: int, timeout: float = 0.0
) -> _Token | None:
    """Attempt to acquire an in-process concurrency slot.

    Note: this is per-process (won't coordinate across multiple workers).
    """

    hk = str(host_key or "").strip()
    k = str(kind or "").strip() or "stream"
    lim = int(limit or 0)
    if not hk or lim <= 0:
        return None

    key = (hk, k, lim)
    with _lock:
        sem = _sems.get(key)
        if sem is None:
            sem = threading.Semaphore(lim)
            _sems[key] = sem

    ok = sem.acquire(timeout=max(0.0, float(timeout or 0.0)))
    if not ok:
        return None
    return _Token(sem=sem)


def wait_acquire(
    host_key: str, *, kind: str, limit: int, max_wait_s: float = 0.5
) -> _Token | None:
    """Wait briefly to acquire a slot, backing off with jitter."""

    deadline = time.time() + max(0.0, float(max_wait_s or 0.0))
    while time.time() < deadline:
        tok = try_acquire(host_key, kind=kind, limit=limit, timeout=0.0)
        if tok:
            return tok
        time.sleep(0.05)
    return None
