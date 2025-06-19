import json
import os
import time
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List

LOG_PATH = "data/latency_log.json"
_lock = Lock()


def _load_log() -> List[Dict[str, Any]]:
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_log(entries: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(entries, f)


def profile_route(
    name: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for measuring route execution time."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        route_name = name or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = (time.time() - start) * 1000.0
                with _lock:
                    data = _load_log()
                    data.append(
                        {
                            "route": route_name,
                            "elapsed_ms": elapsed,
                            "timestamp": time.time(),
                        }
                    )
                    _save_log(data)

        return wrapper

    return decorator


def get_latency_stats() -> Dict[str, Dict[str, float | int]]:
    """Return aggregated latency statistics."""
    with _lock:
        data = _load_log()
    stats = {}
    for entry in data:
        route = entry.get("route")
        stats.setdefault(route, {"count": 0, "total": 0.0})
        stats[route]["count"] += 1
        stats[route]["total"] += entry.get("elapsed_ms", 0.0)
    for route, info in stats.items():
        count = info["count"]
        info["average_ms"] = info["total"] / count if count else 0.0
        del info["total"]
    return stats
