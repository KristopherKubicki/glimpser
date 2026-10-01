"""Persistent, bounded browser turns; store camera names, never source secrets."""

import os
import random
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MAX_PENDING = 512
MAX_ATTEMPTS = 8
MAX_AGE = 6 * 3600
LEASE_SECONDS = 150


@contextmanager
def _database(*, write: bool = True):
    from app.config import DATABASE_PATH

    path = Path(
        os.getenv("GLIMPSER_BROWSER_QUEUE_PATH", DATABASE_PATH + ".browser-queue")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        # Readers (health and lease checks) must not hold up writer commits.
        # Persist WAL once for existing queues too; retain SQLite's FULL sync
        # default so a successful lease commit remains durable.
        if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
            mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise sqlite3.OperationalError("Browser queue requires WAL journaling")
        tables = db.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name IN ('turns', 'state')"
        ).fetchone()[0]
        initialized = (
            tables == 2 and db.execute("SELECT 1 FROM state WHERE id=1").fetchone()
        )
        if not initialized:
            # Bootstrap only when needed. Even INSERT OR IGNORE on an existing
            # row acquires a writer lock, so it does not belong on every read.
            db.execute(
                "CREATE TABLE IF NOT EXISTS turns (name TEXT PRIMARY KEY, "
                "queued REAL, ready REAL, priority INTEGER, attempts INTEGER DEFAULT 0, "
                "lease REAL DEFAULT 0, token TEXT DEFAULT '')"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, served INTEGER)"
            )
            db.execute("INSERT OR IGNORE INTO state VALUES (1, 0)")
            db.commit()
        if write:
            db.execute("BEGIN IMMEDIATE")
        else:
            db.execute("PRAGMA query_only=ON")
        yield db
        if write:
            db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def enqueue(name: str, template: dict | None = None) -> bool:
    """Keep one pending turn per camera, preserving its original waiting age."""
    now = time.time()
    groups = set(str((template or {}).get("groups") or "").lower().split(","))
    priority = name.lower().startswith("hubitat") or bool(
        {g.strip() for g in groups} & {"priority", "home", "systems"}
    )
    with _database() as db:
        db.execute(
            "DELETE FROM turns WHERE queued < ? AND lease <= ?", (now - MAX_AGE, now)
        )
        if db.execute("SELECT 1 FROM turns WHERE name=?", (name,)).fetchone():
            return True
        if db.execute("SELECT COUNT(*) FROM turns").fetchone()[0] >= MAX_PENDING:
            return False
        db.execute(
            "INSERT INTO turns(name,queued,ready,priority) VALUES(?,?,?,?)",
            (name, now, now, int(priority)),
        )
    return True


def claim() -> dict | None:
    """Lease one turn atomically; reserve three of four turns for home/status views."""
    now = time.time()
    with _database() as db:
        db.execute(
            "DELETE FROM turns WHERE lease <= ? AND (queued < ? OR attempts >= ?)",
            (now, now - MAX_AGE, MAX_ATTEMPTS),
        )
        # A process restart or overlapping scheduler must not launch another render.
        if db.execute("SELECT 1 FROM turns WHERE lease > ?", (now,)).fetchone():
            return None
        served = db.execute("SELECT served FROM state WHERE id=1").fetchone()[0]
        ordering = "priority DESC, queued" if served % 4 != 3 else "queued"
        row = db.execute(
            f"SELECT * FROM turns WHERE ready <= ? ORDER BY {ordering}, name LIMIT 1",
            (now,),
        ).fetchone()
        if row is None:
            return None
        token = uuid.uuid4().hex
        db.execute(
            "UPDATE turns SET lease=?, token=?, attempts=attempts+1 WHERE name=?",
            (now + LEASE_SECONDS, token, row["name"]),
        )
        db.execute("UPDATE state SET served=served+1 WHERE id=1")
        return {"name": row["name"], "token": token}


def owns_lease(name: str, token: str) -> bool:
    """Reject late/offline replays of an expired or reassigned worker lease."""
    with _database(write=False) as db:
        return (
            db.execute(
                "SELECT 1 FROM turns WHERE name=? AND token=? AND lease > ?",
                (name, token, time.time()),
            ).fetchone()
            is not None
        )


def capture_is_current(template: dict, now: float | None = None) -> bool:
    """Return whether an accepted frame still meets its configured interval.

    External producers and delayed captures can publish just before the next
    scheduled tick. Re-rendering them immediately wastes scarce browser time.
    Failed, stale, missing and future-dated frames never suppress a capture.
    """
    if template.get("last_capture_status") != "fresh" or template.get("capture_failed"):
        return False
    try:
        stamp = datetime.fromisoformat(
            str(template.get("last_screenshot_time") or "").replace("Z", "+00:00")
        )
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = (time.time() if now is None else now) - stamp.timestamp()
        interval = max(1, int(template.get("frequency") or 30)) * 60
        return 0 <= age < interval
    except (ValueError, TypeError, OverflowError):
        return False


def satisfied(name: str, token: str, template: dict) -> bool:
    """A newer accepted capture can satisfy a waiting turn, never a stale retry."""
    if template.get("last_capture_status") != "fresh" or template.get("capture_failed"):
        return False
    try:
        stamp = datetime.fromisoformat(
            str(template.get("last_screenshot_time") or "").replace("Z", "+00:00")
        )
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        captured = stamp.timestamp()
    except (ValueError, TypeError, OverflowError):
        return False
    now = time.time()
    with _database(write=False) as db:
        row = db.execute(
            "SELECT queued FROM turns WHERE name=? AND token=? AND lease > ?",
            (name, token, now),
        ).fetchone()
        return bool(
            row
            and (row["queued"] <= captured <= now or capture_is_current(template, now))
        )


def finish(
    name: str, token: str, retry: bool = False, *, attempted: bool = True
) -> None:
    """Acknowledge this lease only; back off busy turns without losing queue age."""
    with _database() as db:
        row = db.execute(
            "SELECT attempts FROM turns WHERE name=? AND token=?", (name, token)
        ).fetchone()
        if row is None:
            return
        attempts = row["attempts"] if attempted else max(0, row["attempts"] - 1)
        if retry and attempts < MAX_ATTEMPTS:
            # CPU/memory deferrals and a busy browser are local contention, not
            # failed source attempts. Preserve the ticket and its waiting age.
            delay = (
                min(90, 5 * 2 ** max(0, attempts - 1)) if attempted else 30
            ) + random.uniform(0, 5)
            db.execute(
                "UPDATE turns SET lease=0, token='', ready=?, attempts=? WHERE name=? AND token=?",
                (time.time() + delay, attempts, name, token),
            )
        else:
            db.execute("DELETE FROM turns WHERE name=? AND token=?", (name, token))


def health() -> dict:
    """Return counts and oldest waiting age without exposing camera sources."""
    now = time.time()
    with _database(write=False) as db:
        row = db.execute(
            "SELECT COUNT(*) AS pending, MIN(queued) AS oldest, "
            "COALESCE(SUM(lease > ?),0) AS active FROM turns",
            (now,),
        ).fetchone()
        return {
            "pending": row["pending"],
            "active": row["active"],
            "oldest_wait_seconds": round(max(0, now - (row["oldest"] or now))),
        }
