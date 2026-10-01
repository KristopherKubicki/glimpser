"""Private, opt-in capture tuning and dashboard presentation settings."""

import ipaddress
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def _host(value):
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ValueError("Invalid host")
    value = value.lower()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value):
            raise ValueError("Invalid host") from None
    return value


def _label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError("Invalid capture label")
    return value.strip()


def caption_image_size(name: str | None) -> int:
    """Preserve detail for configured feeds and device dashboards within fixed bounds."""
    name = str(name or "")
    if name.startswith("Hubitat"):
        return 1536
    if name in CAPTURE_POLICY.get("caption_detail_cameras", []) or any(
        name.startswith(prefix)
        for prefix in CAPTURE_POLICY.get("caption_detail_prefixes", [])
    ):
        return 1024
    return 512


def load_capture_policy() -> dict:
    """Read bounded private JSON once at startup; invalid settings add no exceptions."""
    path = os.getenv("GLIMPSER_CAPTURE_POLICY", "").strip()
    if not path:
        return {}
    try:
        with Path(path).expanduser().open(encoding="utf-8") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Policy too large")
        data = json.loads(raw)
        policy = {}
        for key in ("hubitat_hosts", "admin_excluded_hosts", "admin_hosts"):
            values = data.get(key, [])
            if not isinstance(values, list):
                raise ValueError("Expected host list")
            policy[key] = [_host(value) for value in values]
        entries = data.get("variable_size_images", [])
        if not isinstance(entries, list):
            raise ValueError("Expected image list")
        images = []
        for entry in entries:
            host = _host(entry["host"])
            path = entry["path"]
            if (
                not isinstance(path, str)
                or not path.startswith("/")
                or len(path) > 2048
                or urlsplit(path).path != path
                or path.startswith("//")
            ):
                raise ValueError("Expected exact URL path")
            images.append({"host": host, "path": path})
        policy["variable_size_images"] = images
        for key in (
            "caption_detail_cameras",
            "caption_detail_prefixes",
            "slow_rtsp_cameras",
        ):
            values = data.get(key, [])
            if not isinstance(values, list) or len(values) > 1024:
                raise ValueError("Invalid caption detail settings")
            policy[key] = [_label(value) for value in values]
        labels = data.get("dashboard_camera_labels", {})
        if not isinstance(labels, dict) or len(labels) > 1024:
            raise ValueError("Invalid dashboard labels")
        policy["dashboard_camera_labels"] = {
            _label(name): _label(label) for name, label in labels.items()
        }
        return policy
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logging.warning("Invalid capture policy; host exceptions disabled")
        return {}


CAPTURE_POLICY = load_capture_policy()


def variable_size_image(url: str) -> bool:
    """Match HTTP(S) image host and case-sensitive path, never URL substrings."""
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and any(
            parsed.hostname == entry["host"] and parsed.path == entry["path"]
            for entry in CAPTURE_POLICY.get("variable_size_images", [])
        )
    except ValueError:
        return False
