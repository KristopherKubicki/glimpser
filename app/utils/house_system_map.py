"""Read-only home service inventory and bounded, cached TCP observations.

This is a logical placement map, not discovered switch-port topology. Isolated
compute is deliberately never probed from the camera guest.
"""

import copy
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.status_config import STATUS_CONFIG

NODES = STATUS_CONFIG.get("nodes", [])
GROUPS = ("Home control", "Personal compute", "Work compute")
_LOCK = threading.Lock()
_CACHE = None
_CACHE_AT = 0.0
TTL_SECONDS = 30


def _probe(node):
    """Observe only the configured port; never run commands or discover hosts."""
    key, name, group, address, port, role, link, protocol = node
    row = {
        "id": key,
        "name": name,
        "group": group,
        "address": address,
        "role": role,
        "link": link,
        "protocol": protocol,
        "port": port,
    }
    if port is None:
        row.update(status="isolated", label="Not probed · isolated", elapsed_ms=None)
        return row
    started = time.monotonic()
    try:
        with socket.create_connection((address, port), timeout=0.7):
            pass
        row.update(status="responding", label=f"{protocol} responding")
    except OSError:
        row.update(status="unreachable", label=f"{protocol} unreachable from Glimpser")
    row["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return row


def snapshot():
    """Return a fresh-enough immutable copy, coalescing concurrent page requests."""
    global _CACHE, _CACHE_AT
    with _LOCK:
        if _CACHE is not None and time.monotonic() - _CACHE_AT < TTL_SECONDS:
            return copy.deepcopy(_CACHE)
        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(_probe, NODES))
        _CACHE = {
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nodes": rows,
            "responding": sum(r["status"] == "responding" for r in rows),
            "unreachable": sum(r["status"] == "unreachable" for r in rows),
            "isolated": sum(r["status"] == "isolated" for r in rows),
        }
        _CACHE_AT = time.monotonic()
        return copy.deepcopy(_CACHE)
