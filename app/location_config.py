"""Private, optional site metadata for the offline camera census."""

import json
import logging
import math
import os
from pathlib import Path
from urllib.parse import urlsplit


def _text(value, maximum=240):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Invalid location text")
    return value.strip()


def load_location_config():
    """Return validated site seeds; invalid input never supplies location defaults."""
    path = Path(
        os.getenv(
            "GLIMPSER_LOCATION_CONFIG",
            str(Path.home() / ".config/glimpser/location_config.json"),
        )
    ).expanduser()
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Location configuration too large")
        sites = json.loads(raw)["sites"]
        if not isinstance(sites, list) or len(sites) > 64:
            raise ValueError("Invalid site inventory")
        result = []
        for site in sites:
            groups = site.get("groups", [])
            prefixes = site.get("url_prefixes", [])
            if any(not isinstance(v, list) or len(v) > 64 for v in (groups, prefixes)):
                raise ValueError("Invalid site selectors")
            groups = [_text(v).lower() for v in groups]
            prefixes = [_text(v, 512).lower() for v in prefixes]
            for prefix in prefixes:
                parsed = urlsplit(prefix)
                if (
                    parsed.scheme not in {"http", "https", "rtsp", "sdm", "eufy"}
                    or not parsed.netloc
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("Invalid site URL prefix")
            if not groups and not prefixes:
                raise ValueError("Missing site selectors")
            latitude, longitude = site.get("latitude"), site.get("longitude")
            if (latitude is None) != (longitude is None):
                raise ValueError("Incomplete coordinates")
            for value, bound in ((latitude, 90), (longitude, 180)):
                if value is not None and (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not -bound <= value <= bound
                ):
                    raise ValueError("Invalid coordinates")
            private = site.get("private", True)
            accuracy = site.get("accuracy", "site")
            if type(private) is not bool or accuracy not in {
                "exact",
                "approximate",
                "site",
                "region",
                "source",
            }:
                raise ValueError("Invalid location classification")
            result.append(
                {
                    "groups": groups,
                    "url_prefixes": prefixes,
                    "label": _text(site["label"]),
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": accuracy,
                    "private": private,
                    "evidence": _text(site["evidence"], 2000),
                }
            )
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logging.warning("Invalid location configuration; site seeding disabled")
        return []
