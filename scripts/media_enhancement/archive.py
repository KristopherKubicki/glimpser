"""Bounded local retention of completed night jobs; never deletes image data."""

import hashlib
import os
import re
import shutil

from app.utils.enhancement_review import archive_root
from scripts.feed_tv.core import read, write

TARGET_BYTES = 3 * 1024**3
ARCHIVE_BYTES = 16 * 1024**3


def archive_completed(root, now):
    """Move old unreferenced night jobs under the caller's integration lock.

    Keep five newest per camera/pool, explicit review decisions and all live
    indexes. Same-filesystem rename preserves originals atomically; review asset
    resolution supports the archive. This is local retention, not a backup.
    """
    archive = archive_root(root)
    if archive.is_symlink():
        return {"state": "held", "reason": "archive_symlink"}
    used = sum(
        p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()
    )
    if used <= TARGET_BYTES:
        return {"state": "within_budget", "moved": 0, "bytes": 0}
    indexes = []
    for path in (root / "live-index").glob("*.json"):
        row = read(path)
        if (
            path.is_symlink()
            or not isinstance(row, dict)
            or not re.fullmatch(r"[a-f0-9]{64}", str(row.get("id", "")))
        ):
            return {"state": "held", "reason": "invalid_live_index"}
        indexes.append(row["id"])
    rows = []
    for path in root.glob("*/job.json"):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        row = read(path)
        if (
            isinstance(row, dict)
            and row.get("id") == path.parent.name
            and re.fullmatch(r"[a-f0-9]{64}", path.parent.name)
            and row.get("profile") == "night-adaptive"
            and row.get("state") == "ready"
            and type(row.get("captured_at")) in (int, float)
        ):
            rows.append(row)
    rows.sort(key=lambda r: r["captured_at"], reverse=True)
    counts, eligible = {}, []
    for row in rows:
        key = (row.get("camera"), row.get("pool"))
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= 5 or row["id"] in indexes or row.get("quality_review"):
            continue
        if now - row["captured_at"] >= 3 * 3600:
            eligible.append(row)
    archive.mkdir(mode=0o700, exist_ok=True)
    if archive.stat().st_dev != root.stat().st_dev:
        return {"state": "held", "reason": "archive_requires_same_filesystem"}
    archive_used = sum(p.stat().st_size for p in archive.rglob("*") if p.is_file())
    moved, total = 0, 0
    for row in reversed(eligible):
        if used <= TARGET_BYTES or moved >= 64:
            break
        source, dest = root / row["id"], archive / row["id"]
        files = list(source.iterdir())
        if (
            dest.exists()
            or dest.is_symlink()
            or any(p.is_symlink() or not p.is_file() for p in files)
        ):
            continue
        size = sum(p.stat().st_size for p in files)
        if (
            archive_used + size + 8192 > ARCHIVE_BYTES
            or shutil.disk_usage(root).free < 15 * 1024**3
        ):
            break
        # Validate recovery inputs before moving. Bad jobs stay in place for diagnosis.
        expected = {
            "source": row.get("sha256"),
            "enhanced.png": (row.get("processing") or {}).get("sha256"),
        }
        valid = True
        for name, digest in expected.items():
            path = source / name
            if not path.is_file() or path.stat().st_size > 64 * 1024**2:
                valid = False
                break
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024**2), b""):
                    hasher.update(chunk)
            if hasher.hexdigest() != digest:
                valid = False
                break
        if not valid:
            continue
        receipt = {
            "prepared_at": now,
            "state": "prepared",
            "id": row["id"],
            "bytes": size,
            "verified_hashes": expected,
            "local_only": True,
        }
        # Preserve verified recovery evidence before the atomic move. If the
        # final receipt write fails, the prepared receipt travels with the job.
        write(source / "archive-receipt.json", receipt)
        os.rename(source, dest)
        write(
            dest / "archive-receipt.json",
            {
                **receipt,
                "state": "complete",
                "archived_at": now,
            },
        )
        moved += 1
        total += size
        used -= size
        archive_used += size + 8192
    return {"state": "complete", "moved": moved, "bytes": total}
