"""Simple request throttling utilities."""

from __future__ import annotations

import time
import logging
from functools import wraps
from typing import Callable, Dict, Tuple

from flask import request, abort

# Map of (IP address, endpoint) to last access timestamp
_last_calls: Dict[Tuple[str, str], float] = {}


def clear() -> None:
    """Clear all stored throttle information."""
    _last_calls.clear()


def limit_rate(seconds: int) -> Callable[[Callable], Callable]:
    """Limit calls from a single IP to once every ``seconds`` seconds."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or "unknown"
            key = (ip, func.__name__)
            now = time.time()
            last = _last_calls.get(key, float("-inf"))
            if now - last < seconds:
                logging.warning("Throttled %s from %s", func.__name__, ip)
                abort(429)
            _last_calls[key] = now
            return func(*args, **kwargs)

        return wrapper

    return decorator
