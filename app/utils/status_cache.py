"""Cache HTTP status codes for network resources.

The cache stores simple ``{url: (code, time)}`` mappings to avoid
re-checking unreachable cameras or endpoints too frequently.  Results are
persisted to disk so that restarts retain historical success or failure
information.
"""

import json
import logging
import os
import time

STATUS_CACHE_TTL = 60 * 60  # 1 hour
STATUS_CACHE_PATH = "data/status_cache.json"

status_code_cache: dict[str, int] = {}
status_code_cache_time: dict[str, float] = {}


def _load_status_cache() -> None:
    """Load cached status codes from ``STATUS_CACHE_PATH``."""
    if not os.path.exists(STATUS_CACHE_PATH):
        return
    try:
        with open(STATUS_CACHE_PATH) as f:
            data = json.load(f)
    except Exception:
        return

    status_code_cache.clear()
    status_code_cache_time.clear()
    for url, info in data.items():
        status_code_cache[url] = info.get("code")
        status_code_cache_time[url] = info.get("time", 0)


def _persist_status_cache() -> None:
    """Write ``status_code_cache`` to ``STATUS_CACHE_PATH``."""
    os.makedirs(os.path.dirname(STATUS_CACHE_PATH), exist_ok=True)
    data = {
        url: {"code": code, "time": status_code_cache_time.get(url, 0)}
        for url, code in status_code_cache.items()
    }
    try:
        with open(STATUS_CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        logging.exception("Failed to persist status cache")


_load_status_cache()


def get_cached_status_code(url: str) -> int | None:
    """Return cached HTTP status code for URL if not expired."""
    code = status_code_cache.get(url)
    ts = status_code_cache_time.get(url, 0)
    if code is not None and time.time() - ts < STATUS_CACHE_TTL:
        return code
    if code is not None:
        status_code_cache.pop(url, None)
        status_code_cache_time.pop(url, None)
        _persist_status_cache()
    return None


def set_cached_status_code(url: str, code: int) -> None:
    """Store status code for URL with current timestamp."""
    status_code_cache[url] = code
    status_code_cache_time[url] = time.time()
    _persist_status_cache()
