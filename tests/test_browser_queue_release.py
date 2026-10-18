"""Idle browser queues avoid probes and exceptions promptly release leases."""

from unittest.mock import Mock

import pytest

from app.utils import browser_queue as queue
from app.utils import scheduling as sc


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setattr(queue.time, "time", lambda: 1000.0)
    monkeypatch.setattr(sc, "_shutdown_event", Mock(is_set=lambda: False))
    monkeypatch.setattr(sc, "get_template", lambda _: {"browser": True})
    monkeypatch.setattr(sc, "is_system_online", lambda: True)


def test_empty_queue_never_checks_connectivity(configured, monkeypatch):
    probe = Mock(side_effect=AssertionError("idle loop opened network probe"))
    monkeypatch.setattr(sc, "is_system_online", probe)
    sc.process_browser_queue()
    probe.assert_not_called()


def test_removed_template_never_checks_connectivity(configured, monkeypatch):
    queue.enqueue("camera", {})
    monkeypatch.setattr(sc, "get_template", lambda _: None)
    probe = Mock(side_effect=AssertionError("discarded ticket opened probe"))
    monkeypatch.setattr(sc, "is_system_online", probe)
    sc.process_browser_queue()
    probe.assert_not_called()
    assert queue.health()["pending"] == 0


@pytest.mark.parametrize("failure", ["lookup", "probe", "worker"])
def test_parent_exception_releases_claim_immediately(configured, monkeypatch, failure):
    queue.enqueue("camera", {})
    target = {
        "lookup": "get_template",
        "probe": "is_system_online",
        "worker": "run_with_timeout",
    }[failure]
    monkeypatch.setattr(sc, target, Mock(side_effect=RuntimeError("injected failure")))
    with pytest.raises(RuntimeError, match="injected failure"):
        sc.process_browser_queue()
    assert queue.health()["pending"] == 1
    assert queue.health()["active"] == 0
    queue.enqueue("another", {})
    assert queue.claim()["name"] == "another"


def test_offline_releases_ticket_without_consuming_attempt(configured, monkeypatch):
    queue.enqueue("camera", {})
    monkeypatch.setattr(sc, "is_system_online", lambda: False)
    worker = Mock()
    monkeypatch.setattr(sc, "run_with_timeout", worker)
    sc.process_browser_queue()
    worker.assert_not_called()
    with queue._database(write=False) as db:
        row = db.execute("select attempts,lease,ready from turns").fetchone()
    assert row["attempts"] == 0
    assert row["lease"] == 0
    assert row["ready"] > 1000
