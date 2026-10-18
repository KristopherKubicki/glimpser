#!/usr/bin/env python3
"""Retain a bounded pilot history of existing clean captures, without polling cameras."""

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.feed_tv.core import lock, write
from scripts.media_enhancement.queue import MAX_LIBRARY_BYTES, ROOT
from scripts.media_enhancement.worker import MAX_RESULT, MAX_SOURCE, probe

# Interleave locations so the first pass covers the estate before extra angles.
# Only read existing captures: enrollment never changes camera polling.
CAMERAS = (
    "BeachSouthJetty",
    "BeachShore",
    "Street",
    "Argyle100",
    "Halsted_Google_Showroom_Mid",
    "BeachDriveway",
    "Driveway",
    "ArgyleEntryFisheye",
    "Halsted_Google_Bookcase",
    "BeachPathway",
    "Backyard",
    "ArgyleShowroomWide",
    "Halsted_Google_Backroom",
    "BeachBioswale",
    "BeachGravel",
    "BeachMapleTree",
    "Beach_Google_Backyard",
    "Beach_Google_Front_Yard",
    "Halsted",
    "Halsted019",
    "FrontDoor",
    "Argyle300",
    "Argyle400",
    "Argyle500",
    "Beach_Google_Basement",
    "Beach_Google_Front_Door",
    "Beach_Google_Foyer",
)
DATA = Path("/home/kristopher/code/glimpser/data/screenshots")


# Disposable history must not consume the space reserved for review derivatives.
MAX_HISTORY_BYTES = 384 * 1024**2


def prune_history(history, now, maximum=MAX_HISTORY_BYTES):
    """Prune only owned disposable copies, under the collector/snapshot lock."""
    retained = []
    removed = 0
    for camera in CAMERAS:
        dest = history / camera
        if dest.is_symlink():
            continue
        owned = sorted(
            p
            for p in dest.glob("*.png")
            if re.fullmatch(r"\d{14}\.png", p.name) and not p.is_symlink()
        )
        for index, path in enumerate(owned):
            stat = path.stat()
            if index < len(owned) - 93 or stat.st_mtime < now - 48 * 3600:
                path.unlink()
                path.with_suffix(".json").unlink(missing_ok=True)
                removed += 1
            else:
                metadata = path.with_suffix(".json")
                size = stat.st_size
                if metadata.is_file() and not metadata.is_symlink():
                    size += metadata.stat().st_size
                retained.append((stat.st_mtime, str(path), path, size))
    total = sum(row[3] for row in retained)
    for _, _, path, size in sorted(retained):
        if total <= maximum:
            break
        path.unlink()
        path.with_suffix(".json").unlink(missing_ok=True)
        total -= size
        removed += 1
    return removed


def collect(root=ROOT, data=DATA, now=None):
    now = time.time() if now is None else now
    history = root / "clean-history"
    count = 0
    with lock(root, "collect"):
        history.mkdir(exist_ok=True, mode=0o700)
        # Complete retention for every camera before an admission check can exit.
        pruned = prune_history(history, now)
        for camera in CAMERAS:
            dest = history / camera
            if dest.is_symlink() or (data / camera).is_symlink():
                continue
            dest.mkdir(exist_ok=True, mode=0o700)
            for source in sorted((data / camera).glob("*.clean.png"))[-3:]:
                match = re.fullmatch(
                    re.escape(camera) + r"_(\d{14})\.png\.clean\.png", source.name
                )
                if not match or source.is_symlink():
                    continue
                stamp = (
                    dt.datetime.strptime(match[1], "%Y%m%d%H%M%S")
                    .replace(tzinfo=dt.timezone.utc)
                    .timestamp()
                )
                if not now - 900 <= stamp <= now:
                    continue
                target = dest / (match[1] + ".png")
                if target.exists():
                    continue
                if (
                    shutil.disk_usage(root).free < 15 * 1024**3
                    or sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
                    + MAX_SOURCE
                    + MAX_RESULT
                    > MAX_LIBRARY_BYTES
                ):
                    write(
                        root / "collection-status.json",
                        {
                            "checked_at": now,
                            "copied": count,
                            "cameras": list(CAMERAS),
                            "state": "deferred",
                            "reason": "storage_budget",
                            "pruned_history_copies": pruned,
                        },
                    )
                    return count
                temp = target.with_suffix(".partial")
                try:
                    with source.open("rb") as stream:
                        payload = stream.read(MAX_SOURCE + 1)
                    if not 0 < len(payload) <= MAX_SOURCE:
                        continue
                    temp.write_bytes(payload)
                    geometry = probe(temp)
                    if geometry["duration"] != 0:
                        continue
                    write(
                        target.with_suffix(".json"),
                        {
                            "camera": camera,
                            "captured_at": stamp,
                            "source_name": source.name,
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "geometry": geometry,
                            "clean": True,
                        },
                    )
                    os.replace(temp, target)
                    count += 1
                    pruned += prune_history(history, now)
                except (FileNotFoundError, ValueError, subprocess.SubprocessError):
                    # Capture cleanup can race this reader; try the next completed frame.
                    continue
                finally:
                    temp.unlink(missing_ok=True)
        write(
            root / "collection-status.json",
            {
                "checked_at": now,
                "copied": count,
                "cameras": list(CAMERAS),
                "state": "complete",
                "pruned_history_copies": pruned,
            },
        )
    return count


if __name__ == "__main__":
    os.umask(0o077)
    print(json.dumps({"copied": collect()}))
