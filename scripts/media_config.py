"""Private installation settings for existing personal media workers.

This module deliberately has no application, credential or network imports.
"""

import json
import os
import re
from pathlib import Path


def load_media_config():
    """Read a bounded, personal-only registry; never choose a fallback account."""
    path = Path(
        os.getenv(
            "GLIMPSER_MEDIA_CONFIG",
            str(Path.home() / ".config/glimpser/media_config.json"),
        )
    ).expanduser()
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Media configuration too large")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("scope") != "personal":
        raise ValueError("Personal media configuration required")
    for key in ("personal_review_host", "tuner_host"):
        value = data.get(key, "")
        if not isinstance(value, str) or (
            value and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}", value)
        ):
            raise ValueError("Invalid media host")
    for key in ("data_root", "ssh_identity"):
        if key in data and (
            not isinstance(data[key], str)
            or not Path(data[key]).expanduser().is_absolute()
        ):
            raise ValueError("Expected absolute local path")
    cameras = data.get("collect_cameras", [])
    magazine = data.get("magazine_cameras", {})
    if (
        not isinstance(cameras, list)
        or not isinstance(magazine, dict)
        or len(cameras) > 1024
        or len(magazine) > 1024
    ):
        raise ValueError("Invalid media camera inventory")
    for name in [*cameras, *magazine]:
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name
        ):
            raise ValueError("Invalid camera name")
    if any(
        not isinstance(label, str) or not 1 <= len(label) <= 240
        for label in magazine.values()
    ):
        raise ValueError("Invalid media camera label")
    return data


def review_command(kind):
    """Select a fixed worker on the explicitly configured personal SSH target."""
    workers = {
        "feed_tv": ".local/lib/glimpser-feed-tv/review_worker.py",
        "magazine": ".local/lib/glimpser-magazine/review.py",
    }
    if kind not in workers:
        raise ValueError("Unknown review worker")
    config = load_media_config()
    host = config.get("personal_review_host")
    if not host:
        raise RuntimeError("Personal review host is not configured")
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
    ]
    if config.get("ssh_identity"):
        command.extend(["-i", str(Path(config["ssh_identity"]).expanduser())])
    return [*command, host, "python3", workers[kind]]
