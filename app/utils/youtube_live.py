"""Resolve configured public YouTube camera broadcasts without browser sessions."""

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_cache = {}
_lock = threading.Lock()


def video_id(url: str) -> str | None:
    """Accept exact public video/thumbnail hosts, never arbitrary extractor URLs."""
    try:
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return None
        host = parsed.hostname
        if host in {"i.ytimg.com", "img.youtube.com"}:
            match = re.fullmatch(r"/vi(?:_webp)?/([\w-]{11})/[^/]+", parsed.path)
            candidate = match[1] if match else ""
        elif host == "youtu.be":
            candidate = parsed.path.strip("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            candidate = parse_qs(parsed.query).get("v", [""])[0]
            if not candidate:
                match = re.fullmatch(r"/(?:live|embed)/([\w-]{11})/?", parsed.path)
                candidate = match[1] if match else ""
        else:
            return None
        return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None
    except ValueError:
        return None


def monitored_id(ident: str, path: Path | None = None) -> str:
    """Use only a recent same-channel replacement verified by our personal monitor."""
    path = path or Path.home() / ".local/share/glimpser-feed-tv/youtube.json"
    try:
        registry = json.loads(path.read_text())
        for row in registry.get("sources", {}).values():
            if (
                row.get("original_id") == ident
                and row.get("state") == "live"
                and (row.get("current_id") == ident or row.get("view_verified") is True)
                and 0 <= time.time() - float(row.get("verified_at", 0)) <= 1800
                and re.fullmatch(r"UC[A-Za-z0-9_-]{22}", str(row.get("channel_id", "")))
                and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(row.get("current_id", "")))
            ):
                return row["current_id"]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ident


def resolve(url: str) -> str | None:
    """Return a briefly cached live-only media URL; bound work and reject VOD."""
    ident = video_id(url)
    if not ident:
        return None
    ident = monitored_id(ident)
    now = time.monotonic()
    cached = _cache.get(ident)
    if cached and cached[0] > now:
        return cached[1]
    # Never queue multiple expensive extractors behind a slow public provider.
    if not _lock.acquire(blocking=False):
        return None
    try:
        cached = _cache.get(ident)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        result = None
        try:
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "yt_dlp",
                    "--ignore-config",
                    "--no-playlist",
                    "--skip-download",
                    "--socket-timeout",
                    "5",
                    "--retries",
                    "0",
                    "--extractor-retries",
                    "0",
                    "-f",
                    "best[protocol^=m3u8][height<=720]/best[height<=720]",
                    "--dump-single-json",
                    f"https://www.youtube.com/watch?v={ident}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            info = json.loads(run.stdout)
            media = urlparse(str(info.get("url") or ""))
            if (
                info.get("id") == ident
                and info.get("live_status") == "is_live"
                and media.scheme == "https"
                and media.hostname
                and media.hostname.endswith(".googlevideo.com")
                and not media.username
                and not media.password
            ):
                result = info["url"]
        except (subprocess.SubprocessError, OSError, ValueError, TypeError):
            pass
        if len(_cache) >= 128:
            _cache.clear()
        _cache[ident] = (time.monotonic() + (60 if result else 120), result)
        return result
    finally:
        _lock.release()
