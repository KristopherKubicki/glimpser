"""Validate opt-in household configuration without distributed personal defaults."""

import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def _text(value, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Invalid configuration text")
    return value.strip()


def _identifier(value):
    value = _text(value, 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid identifier")
    return value


def load_household_config() -> dict:
    """Read private JSON at startup; absent or invalid settings disable integration."""
    path = os.getenv("GLIMPSER_HOUSEHOLD_CONFIG", "").strip()
    if not path:
        return {}
    try:
        with Path(path).expanduser().open(encoding="utf-8") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Configuration too large")
        data = json.loads(raw)
        hub = urlsplit(_text(data["hub_url"], 512))
        if (
            hub.scheme not in {"http", "https"}
            or not hub.hostname
            or hub.username is not None
            or hub.password is not None
            or hub.path not in {"", "/"}
            or hub.query
            or hub.fragment
        ):
            raise ValueError("Invalid hub endpoint")
        hub.port  # Validate the port without exposing the URL in errors.
        subjects = {}
        for key, spec in data.get("subjects", {}).items():
            key = _identifier(key)
            item = {"label": _text(spec["label"])}
            if spec.get("location_device"):
                item["location_device"] = _identifier(spec["location_device"])
            if not isinstance(spec.get("gps", False), bool):
                raise ValueError("GPS opt-in must be boolean")
            item["gps"] = spec.get("gps", False)
            if spec.get("location_identity"):
                item["location_identity"] = _text(spec["location_identity"])
            subjects[key] = item
        sources = []
        for spec in data.get("presence_sources", []):
            key = _identifier(spec["subject"])
            if key not in subjects or not isinstance(
                spec.get("heartbeat_required", False), bool
            ):
                raise ValueError("Invalid presence source")
            sources.append(
                {
                    "subject": key,
                    "device": _identifier(spec["device"]),
                    "label": _text(spec["label"]),
                    "heartbeat_required": spec.get("heartbeat_required", False),
                }
            )
        caption = data.get("vehicle_caption", {})
        if caption:
            caption = {
                key: _identifier(caption[key])
                for key in ("camera", "device", "network_device")
            } | {
                "label": _text(caption["label"]),
                "facts": _text(caption["facts"], 4000),
            }
        aliases = []
        for spec in data.get("location_aliases", []):
            key = _identifier(spec["subject"])
            if key not in subjects:
                raise ValueError("Unknown location subject")
            aliases.append(
                {
                    "provider": _identifier(spec["provider"]).lower(),
                    "label": _text(spec["label"]).casefold(),
                    "subject": key,
                }
            )
        return {
            "hub_url": f"{hub.scheme}://{hub.netloc}",
            "subjects": subjects,
            "presence_sources": sources,
            "vehicle_caption": caption,
            "arrival_cameras": [
                _identifier(name) for name in data.get("arrival_cameras", [])
            ],
            "location_aliases": aliases,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logging.warning("Invalid household configuration; integrations disabled")
        return {}
