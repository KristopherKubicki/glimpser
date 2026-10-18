"""Plan and safely prune explicitly managed media, never directory trees."""

import logging
import math
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import (
    CLIPS_DIRECTORY,
    MAX_CLIP_AGE_MINUTES,
    MAX_COMPRESSED_VIDEO_AGE,
    MAX_RAW_DATA_SIZE,
    SCREENSHOT_DIRECTORY,
    VIDEO_DIRECTORY,
    get_setting,
)
from app.utils.screenshots import check_user_activity

_MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"}
_ACTIVE_MARKERS = ("in_process.", "last_motion.", "prev_motion.")
_WRITE_GRACE_SECONDS = 60


@dataclass(frozen=True)
class MediaFile:
    """A regular media file and the identity rechecked before unlink."""

    path: str
    size: int
    mtime: float
    identity: tuple[int, ...]


@dataclass(frozen=True)
class RetentionPlan:
    """An immutable dry-run result; protected bytes may exceed the budget."""

    candidates: tuple[MediaFile, ...]
    total_bytes: int
    retained_bytes: int
    protected_bytes: int
    over_budget_bytes: int
    ignored_entries: int


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _snapshot(path: str) -> MediaFile | None:
    if Path(path).suffix.lower() not in _MEDIA_SUFFIXES:
        return None
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            return None
        return MediaFile(path, info.st_size, info.st_mtime, _identity(info))
    except OSError:
        return None


def get_files_sorted_by_creation_time(directory: str) -> list[str]:
    """List direct regular media oldest first by mtime (legacy API name).

    Linux ctime is metadata-change time, not recording creation time. Do not
    traverse camera symlinks or include directories, sidecars, or partial files.
    """
    if os.path.islink(directory):
        return []
    try:
        with os.scandir(directory) as entries:
            files = [
                item
                for entry in entries
                if (item := _snapshot(os.path.abspath(entry.path))) is not None
            ]
    except OSError:
        logging.warning("Retention directory unavailable: %s", directory)
        return []
    return [
        item.path for item in sorted(files, key=lambda item: (item.mtime, item.path))
    ]


def plan_retention(
    file_list: list[str],
    max_age: float,
    max_size: int | None,
    minimum: int = 10,
    *,
    now: float | None = None,
) -> RetentionPlan:
    """Plan oldest-first eviction, counting protected media against the budget.

    Preserve the newest minimum completed files, active outputs, and files
    modified within the last minute. Limits cover managed media in this list,
    not unknown files, nested directories, or the entire storage volume.
    No filesystem writes occur here. A None size limit disables size eviction.
    """
    if not math.isfinite(max_age) or max_age < 0:
        raise ValueError("max_age must be finite and nonnegative")
    if max_size is not None and (not math.isfinite(max_size) or max_size < 0):
        raise ValueError("max_size must be finite and nonnegative")
    if not isinstance(minimum, int) or minimum < 0:
        raise ValueError("minimum must be a nonnegative integer")
    now = time.time() if now is None else now
    files, ignored = [], 0
    for path in sorted({os.path.abspath(os.fspath(path)) for path in file_list}):
        item = _snapshot(path)
        if item is None:
            ignored += 1
        else:
            files.append(item)
    files.sort(key=lambda item: (item.mtime, item.path))
    active = {
        item.path
        for item in files
        if any(marker in Path(item.path).name for marker in _ACTIVE_MARKERS)
    }
    completed = [item for item in files if item.path not in active]
    newest = {item.path for item in completed[-minimum:]} if minimum else set()
    protected = (
        active
        | newest
        | {item.path for item in files if now - item.mtime < _WRITE_GRACE_SECONDS}
    )
    total = sum(item.size for item in files)
    retained, candidates = total, []
    for item in files:
        if item.path in protected:
            continue
        if now - item.mtime > max_age * 86400 or (
            max_size is not None and retained > max_size
        ):
            candidates.append(item)
            retained -= item.size
    return RetentionPlan(
        tuple(candidates),
        total,
        retained,
        sum(item.size for item in files if item.path in protected),
        max(0, retained - max_size) if max_size is not None else 0,
        ignored,
    )


def _unlink_unchanged(item: MediaFile) -> bool:
    """Unlink an unchanged regular file through a non-symlink parent FD.

    Directory-relative operations avoid redirecting deletion if the parent is
    renamed. Identity checks handle normal capture/rotation churn; POSIX
    stat/unlink is not an atomic lock against hostile concurrent writers.
    """
    parent, name = os.path.split(item.path)
    descriptor = None
    try:
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or _identity(info) != item.identity:
            return False
        os.unlink(name, dir_fd=descriptor)
        return True
    except OSError:
        logging.warning("Retention skipped unavailable or changed media: %s", item.path)
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def delete_old_files(
    file_list: list[str],
    max_age: float,
    max_size: int | None,
    minimum: int = 10,
    *,
    dry_run: bool = False,
) -> dict[str, int | bool]:
    """Plan cleanup, optionally applying unchanged regular-file candidates."""
    plan = plan_retention(file_list, max_age, max_size, minimum)
    removed, removed_bytes = 0, 0
    if not dry_run:
        for item in plan.candidates:
            if _unlink_unchanged(item):
                removed += 1
                removed_bytes += item.size
    result = {
        "dry_run": dry_run,
        "planned_files": len(plan.candidates),
        "planned_bytes": plan.total_bytes - plan.retained_bytes,
        "deleted_files": removed,
        "deleted_bytes": removed_bytes,
        "skipped_files": 0 if dry_run else len(plan.candidates) - removed,
        "total_bytes": plan.total_bytes,
        "protected_bytes": plan.protected_bytes,
        "projected_retained_bytes": plan.retained_bytes,
        "over_budget_bytes": plan.over_budget_bytes,
        "ignored_entries": plan.ignored_entries,
    }
    if plan.candidates or plan.over_budget_bytes:
        logging.info("Retention cleanup: %s", result)
    return result


def cleanup_clips(
    max_age_minutes: int = MAX_CLIP_AGE_MINUTES,
    *,
    dry_run: bool | None = None,
) -> dict[str, int | bool] | None:
    """Prune old regular MP4 clips while idle, using the same safety checks."""
    if dry_run is None:
        dry_run = str(get_setting("RETENTION_DRY_RUN", "true")).lower() != "false"
    if not max_age_minutes or max_age_minutes < 0 or check_user_activity(timeout=1):
        return None
    files = [
        path
        for path in get_files_sorted_by_creation_time(CLIPS_DIRECTORY)
        if Path(path).suffix.lower() == ".mp4"
    ]
    return delete_old_files(
        files, max_age_minutes / 1440, None, minimum=0, dry_run=dry_run
    )


def retention_cleanup(*, dry_run: bool | None = None) -> list[dict[str, int | bool]]:
    """Prune direct camera media only, preserving symlinks and nested trees."""
    if dry_run is None:
        dry_run = str(get_setting("RETENTION_DRY_RUN", "true")).lower() != "false"
    results = []
    for configured_root in (VIDEO_DIRECTORY, SCREENSHOT_DIRECTORY):
        # Configured roots may legitimately link to the data disk.
        root = Path(configured_root).resolve()
        try:
            with os.scandir(root) as cameras:
                for camera in cameras:
                    if not camera.is_dir(follow_symlinks=False):
                        continue
                    files = get_files_sorted_by_creation_time(camera.path)
                    results.append(
                        delete_old_files(
                            files,
                            MAX_COMPRESSED_VIDEO_AGE,
                            MAX_RAW_DATA_SIZE,
                            dry_run=dry_run,
                        )
                    )
        except OSError:
            logging.warning("Retention root unavailable: %s", root)
    clips = cleanup_clips(dry_run=dry_run)
    if clips is not None:
        results.append(clips)
    return results
