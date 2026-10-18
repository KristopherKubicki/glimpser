"""Read private, opt-in camera census location seeds."""

import json
import logging
import math
import os
from pathlib import Path
from urllib.parse import urlsplit


def _text(value, limit=512):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Invalid site text")
    return value.strip()


def _strings(value):
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError("Invalid site selector list")
    return [_text(item).lower() for item in value]


def load_site_locations() -> list[dict]:
    """Load bounded private JSON; absent or invalid files add no location inference."""
    path = os.getenv("GLIMPSER_SITE_LOCATIONS", "").strip()
    if not path:
        return []
    try:
        with Path(path).expanduser().open(encoding="utf-8") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Site configuration too large")
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) > 128:
            raise ValueError("Expected site list")
        sites = []
        for item in data:
            groups = _strings(item.get("groups", []))
            prefixes = _strings(item.get("url_prefixes", []))
            if not groups and not prefixes:
                raise ValueError("Site requires an explicit selector")
            for prefix in prefixes:
                parsed = urlsplit(prefix)
                if (
                    parsed.scheme not in {"http", "https", "rtsp", "eufy", "sdm"}
                    or not parsed.hostname
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("Invalid site URL selector")
                parsed.port
            latitude, longitude = item.get("latitude"), item.get("longitude")
            if (latitude is None) != (longitude is None):
                raise ValueError("Coordinates must be a complete pair")
            if latitude is not None:
                for value, limit in ((latitude, 90), (longitude, 180)):
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not -limit <= value <= limit
                        or not math.isfinite(value)
                    ):
                        raise ValueError("Invalid site coordinates")
            accuracy = item.get("accuracy", "site")
            if accuracy not in {"exact", "approximate", "site", "region", "source"}:
                raise ValueError("Invalid site accuracy")
            private = item.get("private", True)
            if not isinstance(private, bool):
                raise ValueError("Site privacy flag must be boolean")
            sites.append(
                {
                    "groups": groups,
                    "url_prefixes": prefixes,
                    "label": _text(item["label"]),
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": accuracy,
                    "private": private,
                    "evidence": _text(
                        item.get("evidence", "Operator-configured site location"), 2048
                    ),
                }
            )
        return sites
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logging.warning("Invalid site location configuration; location seeds disabled")
        return []
