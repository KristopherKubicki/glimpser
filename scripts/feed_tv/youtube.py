"""Monitor configured public broadcasts and discover replacements on their channels."""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.utils.youtube_live import video_id
from scripts.feed_tv.core import ROOT, lock, read, status, write

VIDEO = re.compile(r"[A-Za-z0-9_-]{11}\Z")
CHANNEL = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")


def extract(url, flat=False):
    args = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--ignore-config",
        "--skip-download",
        "--socket-timeout",
        "5",
        "--retries",
        "0",
        "--extractor-retries",
        "0",
        "--dump-single-json",
    ]
    args += ["--flat-playlist", "--playlist-end", "100"] if flat else ["--no-playlist"]
    result = subprocess.run(
        args + [url], capture_output=True, text=True, timeout=25, check=True
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("invalid_metadata")
    return value


def verified(info, channel=None):
    return (
        VIDEO.fullmatch(str(info.get("id", ""))) is not None
        and CHANNEL.fullmatch(str(info.get("channel_id", ""))) is not None
        and (channel is None or info["channel_id"] == channel)
        and info.get("live_status") == "is_live"
    )


def camera_title(value):
    """Ignore broadcast clock suffixes, but preserve location and viewing direction."""
    value = re.sub(r"\b20\d{2}-\d{2}-\d{2}.*$", "", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def same_view(info, row):
    """Channel ownership alone cannot identify a camera on a multi-site channel."""
    original = camera_title(row.get("original_title"))
    return bool(original and original == camera_title(info.get("title")))


def replacement_candidates(listing, row, current):
    """Scan inexpensive titles first; fully probe at most three matching views."""
    candidates = []
    for entry in listing.get("entries", [])[:100]:
        if not isinstance(entry, dict) or not same_view(entry, row):
            continue
        ident = entry.get("id", "")
        if not isinstance(ident, str) or not VIDEO.fullmatch(ident):
            continue
        if ident != current and ident not in candidates:
            candidates.append(ident)
        if len(candidates) == 3:
            break
    return candidates


def monitor(db, root=ROOT, limit=3):
    with lock(root, "youtube"):
        registry = read(root / "youtube.json", {"sources": {}})
        sources = registry.setdefault("sources", {})
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
            configured = {
                name: video_id(url)
                for name, url in connection.execute("select name,url from templates")
                if video_id(url)
            }
        sources = {name: row for name, row in sources.items() if name in configured}
        for name, ident in configured.items():
            if sources.get(name, {}).get("original_id") != ident:
                sources[name] = {"original_id": ident, "checked_at": 0}
        attempted = 0
        for name in sorted(
            sources, key=lambda name: sources[name].get("checked_at", 0)
        ):
            row = sources[name]
            if attempted >= limit:
                break
            if time.time() < row.get("retry_at", 0):
                continue
            attempted += 1
            current = row.get("current_id", row["original_id"])
            if current != row["original_id"] and not row.get("view_verified"):
                current = row["original_id"]
            try:
                channel = row.get("channel_id")
                try:
                    info = extract("https://www.youtube.com/watch?v=" + current)
                except (subprocess.SubprocessError, OSError, ValueError, TypeError):
                    if not CHANNEL.fullmatch(str(channel or "")):
                        raise
                    info = {}  # A deleted broadcast can still have a trusted channel.
                if (
                    info.get("id") == row["original_id"]
                    and (not channel or info.get("channel_id") == channel)
                    and camera_title(info.get("title"))
                ):
                    row["original_title"] = str(info["title"])[:200]
                if verified(info, channel) and (
                    info["id"] == row["original_id"] or same_view(info, row)
                ):
                    row.update(
                        current_id=info["id"],
                        view_verified=True,
                        channel_id=info["channel_id"],
                        title=str(info.get("title", ""))[:200],
                        state="live",
                        verified_at=time.time(),
                        failures=0,
                        retry_at=time.time() + 300,
                    )
                else:
                    if (
                        CHANNEL.fullmatch(str(info.get("channel_id", "")))
                        and not channel
                    ):
                        row["channel_id"] = info["channel_id"]
                    row["state"] = "ended_or_not_live"
                    row["retry_at"] = time.time() + 1800
                # Look for a replacement only after a feed ends; never hop away
                # from a healthy broadcast merely because its channel has others.
                channel = row.get("channel_id", "")
                if (
                    row["state"] != "live"
                    and CHANNEL.fullmatch(channel)
                    and time.time() >= row.get("discover_after", 0)
                ):
                    row["discover_after"] = time.time() + 21600
                    listing = extract(
                        f"https://www.youtube.com/channel/{channel}/streams", flat=True
                    )
                    for ident in replacement_candidates(listing, row, current):
                        try:
                            candidate = extract(
                                "https://www.youtube.com/watch?v=" + ident
                            )
                        except (
                            subprocess.SubprocessError,
                            OSError,
                            ValueError,
                            TypeError,
                        ):
                            continue
                        if verified(candidate, channel) and same_view(candidate, row):
                            row.update(
                                current_id=ident,
                                view_verified=True,
                                title=str(candidate.get("title", ""))[:200],
                                state="live",
                                verified_at=time.time(),
                                failures=0,
                                retry_at=time.time() + 300,
                            )
                            break
            except (subprocess.SubprocessError, OSError, ValueError, TypeError):
                row["failures"] = row.get("failures", 0) + 1
                row.update(
                    state="check_failed",
                    retry_at=time.time()
                    + min(21600, 300 * 2 ** min(row["failures"], 6)),
                )
            row["checked_at"] = time.time()
            registry = {"checked_at": time.time(), "sources": sources}
            write(root / "youtube.json", registry)
        write(root / "youtube.json", {"checked_at": time.time(), "sources": sources})
        status(root, "youtube", "ok", checked=attempted, sources=len(sources))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    monitor(args.database, args.root, max(1, min(5, args.limit)))
