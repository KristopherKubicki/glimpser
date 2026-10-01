"""Queue readers cannot stall commits or lose durable lease state."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from app.utils import browser_queue as queue


def test_reader_does_not_block_queue_commit(tmp_path, monkeypatch):
    path = tmp_path / "queue.db"
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(path))
    queue.enqueue("first", {})
    reader = sqlite3.connect(path)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM turns").fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(queue.enqueue, "second", {})
        try:
            # Keep the reader open until commit completes. This tests locking,
            # not a one-second disk-latency budget on a busy CI host. A rollback
            # journal still fails with SQLite's lock timeout while held open.
            assert future.result(timeout=15) is True
            assert reader.execute("SELECT count(*) FROM turns").fetchone()[0] == 1
        finally:
            reader.rollback()
            reader.close()
    assert queue.health()["pending"] == 2


def test_existing_queue_migrates_without_losing_lease(tmp_path, monkeypatch):
    path = tmp_path / "queue.db"
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(path))
    # Existing rollback-journal schema, ticket, and token survive activation.
    with sqlite3.connect(path) as db:
        db.execute(
            'CREATE TABLE turns(name TEXT PRIMARY KEY, queued REAL, ready REAL, priority INTEGER, attempts INTEGER DEFAULT 0, lease REAL DEFAULT 0, token TEXT DEFAULT "")'
        )
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY, served INTEGER)")
        db.execute("INSERT INTO state VALUES(1, 7)")
        db.execute(
            'INSERT INTO turns VALUES("camera", 100, 101, 1, 2, 9999999999, "owned")'
        )
    assert queue.owns_lease("camera", "owned")
    with sqlite3.connect(path) as db:
        assert db.execute("pragma journal_mode").fetchone()[0] == "wal"
        assert db.execute("SELECT * FROM turns").fetchone() == (
            "camera",
            100,
            101,
            1,
            2,
            9999999999,
            "owned",
        )
        assert db.execute("SELECT served FROM state").fetchone()[0] == 7
