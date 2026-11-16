"""No-op polling must not compete for SQLite's single writer slot."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.utils import browser_queue as queue


@pytest.mark.parametrize(
    "operation", ["idle", "delayed", "leased", "duplicate", "finished"]
)
def test_noop_during_writer_transaction(tmp_path, monkeypatch, operation):
    path = tmp_path / "queue.sqlite"
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(path))
    queue.health()
    turn = None
    if operation != "idle":
        queue.enqueue("camera", {})
    if operation in {"leased", "finished"}:
        turn = queue.claim()
    if operation == "finished":
        queue.finish(**turn)
    if operation == "delayed":
        with sqlite3.connect(path) as db:
            db.execute("UPDATE turns SET ready=?", (queue.time.time() + 60,))
    writer = sqlite3.connect(path)
    writer.execute("BEGIN IMMEDIATE")
    try:
        if operation == "duplicate":
            assert queue.enqueue("camera", {}) is True
        elif operation == "finished":
            queue.finish(**turn)
        else:
            assert queue.claim() is None
    finally:
        writer.rollback()
        writer.close()


def test_concurrent_duplicate_enqueue_is_unique(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    queue.health()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda _: queue.enqueue("camera", {}), range(16)))
    assert queue.health()["pending"] == 1


def test_expired_ticket_is_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    queue.enqueue("camera", {})
    with queue._database() as db:
        db.execute("UPDATE turns SET queued=0, ready=9999999999")
    assert queue.enqueue("camera", {})
    assert queue.claim()["name"] == "camera"


def test_expired_delayed_ticket_is_pruned(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    queue.enqueue("camera", {})
    with queue._database() as db:
        db.execute("UPDATE turns SET queued=0, ready=9999999999")
    assert queue.claim() is None
    assert queue.health()["pending"] == 0
