import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.utils import browser_queue as queue


@pytest.mark.parametrize("operation", ["health", "owns_lease", "satisfied"])
def test_queue_read_does_not_compete_with_writer(monkeypatch, tmp_path, operation):
    path = tmp_path / "queue.sqlite"
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(path))
    queue.enqueue("camera", {})
    turn = queue.claim()
    writer = sqlite3.connect(path)
    writer.execute("BEGIN IMMEDIATE")
    # An uncommitted mutation must stay invisible to these snapshot readers.
    writer.execute("DELETE FROM turns")
    try:
        if operation == "health":
            assert queue.health()["pending"] == 1
        elif operation == "owns_lease":
            assert queue.owns_lease(**turn)
        else:
            assert (
                queue.satisfied(
                    **turn,
                    template={
                        "last_capture_status": "fresh",
                        "last_screenshot_time": datetime.now(timezone.utc).isoformat(),
                    },
                )
                is True
            )
    finally:
        writer.rollback()
        writer.close()


def test_read_connection_rejects_writes_and_can_bootstrap(monkeypatch, tmp_path):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "new.sqlite"))
    assert queue.health()["pending"] == 0
    with queue._database(write=False) as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM turns")


def test_concurrent_claims_still_grant_only_one_active_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    for i in range(8):
        queue.enqueue(f"camera{i}", {})
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: queue.claim(), range(8)))
    assert sum(turn is not None for turn in claims) == 1
    assert queue.health()["active"] == 1
