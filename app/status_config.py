"""Optional private inventory for bounded, read-only household status checks."""

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from app.capture_policy import _host, _label


def _url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid status URL")
    parsed.port  # Reject invalid ports without logging the endpoint.
    _host(parsed.hostname)
    return value


def load_status_config():
    """Fail closed when the opt-in inventory is absent or invalid."""
    path = os.getenv("GLIMPSER_STATUS_CONFIG", "").strip()
    if not path:
        default_path = Path.home() / ".config/glimpser/status_config.json"
        if default_path.is_file():
            path = str(default_path)
    if not path:
        return {}
    try:
        with Path(path).expanduser().open(encoding="utf-8") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Inventory too large")
        data = json.loads(raw)
        nodes = data.get("nodes", [])
        sensors = data.get("sensors", [])
        if (
            not isinstance(nodes, list)
            or len(nodes) > 64
            or not isinstance(sensors, list)
            or len(sensors) > 64
        ):
            raise ValueError("Invalid inventory")
        clean_nodes = []
        for key, name, group, host, port, role, link, protocol in nodes:
            if port is not None and (type(port) is not int or not 1 <= port <= 65535):
                raise ValueError("Invalid port")
            if link and (not link.startswith("/") or link.startswith("//")):
                _url(link)
            clean_nodes.append(
                (
                    _label(key),
                    _label(name),
                    _label(group),
                    _host(host),
                    port,
                    _label(role),
                    link,
                    _label(protocol),
                )
            )
        clean_sensors = []
        for identity, label, attribute in sensors:
            if (
                not isinstance(identity, str)
                or not identity.isascii()
                or not identity.isdigit()
                or len(identity) > 20
                or attribute not in {"contact", "motion"}
            ):
                raise ValueError("Invalid sensor")
            clean_sensors.append((identity, _label(label), attribute))
        hub = data.get("hub", "")
        if clean_sensors:
            _url(hub)
            if urlsplit(hub).path not in {"", "/"}:
                raise ValueError("Expected hub origin")
        native = data.get("native_event_cameras", {})
        if not isinstance(native, dict) or len(native) > 64:
            raise ValueError("Invalid native event inventory")
        native = {_label(name): _host(host) for name, host in native.items()}
        privacy = data.get("privacy_url", "")
        if privacy:
            _url(privacy)
        return {
            "native_event_cameras": native,
            "privacy_url": privacy,
            "extended_kiosk": data.get("extended_kiosk") is True,
            "nodes": clean_nodes,
            "sensors": clean_sensors,
            "hub": hub.rstrip("/"),
            "site": _label(data.get("site", "Home")),
        }
    except (OSError, ValueError, TypeError, AttributeError):
        logging.warning("Invalid status inventory; household probes disabled")
        return {}


STATUS_CONFIG = load_status_config()
