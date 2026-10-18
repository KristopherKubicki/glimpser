"""Reuse recent successful scheduler probes without retaining offline results."""

import os
import time

from . import network

_TTL_SECONDS = 5.0
_PROBE_SETTINGS = (
    "ONLINE_TEST_URLS",
    "ONLINE_TEST_HOSTS",
    "ONLINE_TEST_PORT",
    "LAN_TEST_HOSTS",
    "DNS_TEST_HOSTS",
    "OFFLINE_GRACE_SECONDS",
    "LAN_GRACE_SECONDS",
    "DNS_GRACE_SECONDS",
    "WAN_GRACE_SECONDS",
)
_success = None


def cached_is_system_online(timeout: int = 3) -> bool:
    """Bound duplicate scheduler checks while preserving prompt failure recovery."""
    global _success

    probe = network.is_system_online
    key = (
        os.getpid(),
        timeout,
        probe,
        tuple(os.getenv(name) for name in _PROBE_SETTINGS),
    )
    cached = _success
    if cached is not None and cached[0] == key and time.monotonic() < cached[1]:
        return True

    # Immutable tuple publication avoids locks inherited by forked workers.
    # Concurrent misses may duplicate a probe; they cannot block worker startup.
    result = probe(timeout=timeout)
    _success = (key, time.monotonic() + _TTL_SECONDS) if result else None
    return result
