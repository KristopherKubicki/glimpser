"""Small, private on-disk contracts shared by the personal feed workers."""

import contextlib
import fcntl
import json
import os
import re
import shutil
import time
from pathlib import Path

ROOT = Path.home() / ".local/share/glimpser-feed-tv"
ID = re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".partial")
    temp.write_text(json.dumps(value, indent=2))
    temp.chmod(0o600)
    os.replace(temp, path)


@contextlib.contextmanager
def lock(root, name):
    root.mkdir(parents=True, exist_ok=True)
    with (root / (name + ".lock")).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # A timer/manual overlap is already being handled by the owner.
            raise SystemExit(0) from None
        yield


def usage(root):
    return sum(
        p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()
    )


def capacity(root, maximum=16 * 1024**3, reserve=15 * 1024**3):
    return usage(root) < maximum and shutil.disk_usage(root).free > reserve


def status(root, worker, state, **details):
    write(
        root / (worker + "-status.json"),
        {"state": state, "checked_at": time.time(), **details},
    )


def clean_buffer(root, now=None):
    """Expire only closed, unselected recorder-owned windows after six hours."""
    now = time.time() if now is None else now
    for folder in (root / "buffer").glob("*"):
        if folder.is_symlink() or not folder.is_dir() or not ID.fullmatch(folder.name):
            continue
        if (folder / "reviewing").exists() and now - (
            folder / "reviewing"
        ).stat().st_mtime < 1800:
            continue
        row = read(folder / "capture.json")
        if (row.get("complete") and row.get("ended", now) < now - 6 * 3600) or (
            not row.get("complete") and row.get("started", now) < now - 3600
        ):
            shutil.rmtree(folder)
