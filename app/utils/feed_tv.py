"""Read-only personal television library; publish manifests are the commit point."""

import datetime as dt
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path.home() / ".local/share/glimpser-feed-tv"
CLIP_ID = re.compile(r"tv-\d{13}-\d{1,3}_\d{1,3}\Z")
ASSETS = {"clip.mp4", "poster.jpg", "captions.vtt"}


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def clips(root=ROOT):
    result = []
    for folder in (root / "clips").glob("tv-*"):
        if folder.is_symlink() or not CLIP_ID.fullmatch(folder.name):
            continue
        row = read(folder / "clip.json")
        review = row.get("review", {})
        if (
            row.get("scope") != "personal"
            or row.get("id") != folder.name
            or not (folder / "clip.mp4").is_file()
            or review.get("usable") is not True
        ):
            continue
        stamp = row.get("recorded_at", 0)
        if not isinstance(stamp, (float, int)):
            continue
        try:
            recorded_label = dt.datetime.fromtimestamp(
                stamp, dt.timezone.utc
            ).isoformat()
        except (ValueError, OverflowError, OSError):
            continue
        result.append(
            {
                "id": folder.name,
                "station": str(row.get("station", ""))[:80],
                "recorded_at": stamp,
                "recorded_label": recorded_label,
                "title": str(review.get("title", "Recorded excerpt"))[:100],
                "observation": str(review.get("observation", ""))[:240],
                "duration": row.get("duration", 0),
                "label": row.get("label", "Recorded excerpt"),
                "video": f"/feed-tv/{folder.name}/clip.mp4",
                "poster": f"/feed-tv/{folder.name}/poster.jpg",
            }
        )
    return sorted(result, key=lambda item: item["recorded_at"], reverse=True)[:50]


def snapshot(root=ROOT):
    registry = read(root / "youtube.json")
    sources = [
        {
            "name": name,
            "state": row.get("state", "pending"),
            "checked_at": row.get("checked_at", 0),
            "title": str(row.get("title", ""))[:200],
        }
        for name, row in registry.get("sources", {}).items()
    ]
    return {
        "checked_at": time.time(),
        "scope": "personal",
        "clips": clips(root),
        "sources": sources,
        "workers": {
            name: read(root / (name + "-status.json"))
            for name in ["youtube", "tv", "review"]
        },
    }


def is_tuner_url(url: str) -> bool:
    """Recognize the configured estate tuner without treating web pages as video."""
    try:
        parsed = urlparse(str(url or ""))
        return bool(
            parsed.scheme == "http"
            and parsed.hostname == "192.168.2.194"
            and parsed.port == 5004
            and not parsed.username
            and not parsed.password
            and re.fullmatch(r"/auto/v\d{1,3}\.\d{1,3}", parsed.path)
        )
    except ValueError:
        return False
