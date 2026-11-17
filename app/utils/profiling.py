"""Tools for measuring and reporting route latency during development."""

import fcntl
import json
import logging
import os
import time
from functools import wraps
from threading import Lock

LOG_PATH = "data/latency_log.json"
_lock = Lock()


def _load_log() -> list:
    """Read the preserved legacy history when statistics are requested."""
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _append_entry(entry: dict) -> None:
    """Append one timing record without rewriting the historical log."""
    os.makedirs(os.path.dirname(os.path.abspath(LOG_PATH)), exist_ok=True)
    # A leading newline isolates a partial last record after a process crash.
    # flock coordinates separate workers as well as this process's thread lock.
    payload = "\n" + json.dumps(entry) + "\n"
    with open(LOG_PATH + ".jsonl", "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.write(payload)
            handle.flush()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _iter_entries():
    """Yield legacy and new records, ignoring incomplete journal entries."""
    yield from _load_log()
    try:
        handle = open(LOG_PATH + ".jsonl", encoding="utf-8")
    except FileNotFoundError:
        return
    with handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        try:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    yield entry
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def profile_route(name=None):
    """Decorator for measuring route execution time."""

    def decorator(func):
        route_name = name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = (time.time() - start) * 1000.0
                with _lock:
                    try:
                        _append_entry(
                            {
                                "route": route_name,
                                "elapsed_ms": elapsed,
                                "timestamp": time.time(),
                            }
                        )
                    except OSError:
                        # Optional telemetry must not replace a route's response
                        # or mask its original exception when storage is full.
                        logging.warning("Unable to append route timing record")

        return wrapper

    return decorator


def get_latency_stats():
    """Return aggregated latency statistics across both history formats."""
    stats = {}
    with _lock:
        for entry in _iter_entries():
            route = entry.get("route")
            stats.setdefault(route, {"count": 0, "total": 0.0})
            stats[route]["count"] += 1
            stats[route]["total"] += entry.get("elapsed_ms", 0.0)
    for route, info in stats.items():
        count = info["count"]
        info["average_ms"] = info["total"] / count if count else 0.0
        del info["total"]
    return stats
