"""Load installation-specific dashboard membership from private configuration."""

import json
import logging
import os
from pathlib import Path


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError("Invalid viewer configuration text")
    return value.strip()


def _names(value):
    if not isinstance(value, list) or len(value) > 1024:
        raise ValueError("Expected bounded name list")
    return [_text(item) for item in value]


def load_viewer_config() -> dict:
    """Return validated settings or generic defaults without logging private values."""
    path = os.getenv("GLIMPSER_VIEWER_CONFIG", "").strip()
    if not path:
        return {}
    try:
        with Path(path).expanduser().open(encoding="utf-8") as stream:
            raw = stream.read(262145)
        if len(raw) > 262144:
            raise ValueError("Viewer configuration too large")
        data = json.loads(raw)
        config = {}
        for key in (
            "quarantined_cameras",
            "security_cameras",
            "security_groups",
            "systems_groups",
            "systems_prefixes",
            "systems_cameras",
            "regional_groups",
            "private_groups",
            "archived_groups",
            "timelapse_groups",
            "status_groups",
            "navigation_groups",
            "google_live_cameras",
            "security_approaches",
            "dashboard_group_order",
        ):
            if key in data:
                values = _names(data[key])
                config[key] = (
                    [v.lower() for v in values]
                    if key.endswith("groups") or key == "dashboard_group_order"
                    else values
                )
        contexts = {}
        for key, sections in data.get("context_views", {}).items():
            if key not in {"arrivals", "property", "beach-conditions"}:
                raise ValueError("Unknown context dashboard")
            contexts[key] = {
                _text(label): _names(names) for label, names in sections.items()
            }
        config["context_views"] = contexts
        config["rotation_review_holds"] = {
            _text(name): _text(reason)
            for name, reason in data.get("rotation_review_holds", {}).items()
        }
        for key in ("priority_handoffs", "preferred_areas"):
            values = data.get(key, {})
            if not isinstance(values, dict) or len(values) > 1024:
                raise ValueError("Invalid dashboard settings")
            config[key] = {
                _text(name): (
                    _names(value) if key == "priority_handoffs" else _text(value)
                )
                for name, value in values.items()
            }
        cameras = data.get("kiosk_live", {})
        if not isinstance(cameras, dict) or len(cameras) > 1024:
            raise ValueError("Invalid kiosk camera settings")
        config["kiosk_live"] = {}
        for name, options in cameras.items():
            if not isinstance(options, dict):
                raise ValueError("Invalid kiosk camera options")
            provider = options.get("provider", "stream")
            profile = options.get("profile", "sub")
            quality = options.get("quality", "kiosk")
            fps = options.get("source_fps")
            if (
                provider not in {"stream", "google"}
                or profile not in {"main", "sub"}
                or quality not in {"auto", "kiosk"}
                or (
                    fps is not None
                    and (
                        isinstance(fps, bool)
                        or not isinstance(fps, (int, float))
                        or not 0 < fps <= 120
                    )
                )
            ):
                raise ValueError("Invalid kiosk stream settings")
            config["kiosk_live"][_text(name)] = {
                "provider": provider,
                "profile": profile,
                "quality": quality,
                "label": _text(options.get("label", name)),
                "source_fps": fps,
            }
        return config
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logging.warning(
            "Invalid viewer configuration; using generic dashboard defaults"
        )
        return {}
