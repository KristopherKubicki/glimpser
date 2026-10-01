"""Keep external uploads and recent accepted captures out of scarce browser slots."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.utils import browser_queue as queue
from app.utils import scheduling


def fresh(age=30, **updates):
    return {
        "last_capture_status": "fresh",
        "last_screenshot_time": datetime.fromtimestamp(
            1000 - age, timezone.utc
        ).isoformat(),
        "frequency": 5,
        "browser": True,
        **updates,
    }


@pytest.fixture
def clocked_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    monkeypatch.setattr(queue.time, "time", lambda: 1000.0)
    monkeypatch.setattr(scheduling, "is_system_online", lambda: True)


@pytest.mark.parametrize(
    "template",
    [
        fresh(age=300),
        fresh(age=-1),
        fresh(last_capture_status="stale_ok"),
        fresh(capture_failed=True),
        fresh(last_screenshot_time="bad"),
    ],
)
def test_unusable_or_due_frame_never_suppresses_work(template):
    assert not queue.capture_is_current(template, 1000)


def test_external_upload_before_queue_ticket_satisfies_it(clocked_queue):
    queue.enqueue("dashboard", {})
    turn = queue.claim()
    assert queue.satisfied(**turn, template=fresh())
    assert not queue.satisfied(**turn, template=fresh(age=301))
    assert not queue.satisfied("dashboard", "wrong-token", fresh())


def test_parent_discards_fresh_ticket_without_fork_or_cpu_gate(
    clocked_queue, monkeypatch
):
    queue.enqueue("dashboard", {})
    monkeypatch.setattr(scheduling, "get_template", lambda name: fresh())
    worker = Mock()
    monkeypatch.setattr(scheduling, "run_with_timeout", worker)
    scheduling.process_browser_queue()
    worker.assert_not_called()
    assert queue.health()["pending"] == 0


def test_due_browser_still_enqueues(clocked_queue, monkeypatch):
    monkeypatch.setattr(scheduling, "get_template", lambda name: fresh(age=301))
    scheduling.schedule_camera_capture("dashboard", {}, 120)
    assert queue.health()["pending"] == 1


@pytest.mark.parametrize(
    "template", [fresh(), fresh(age=999, source_template="hubitat_site_dashboard")]
)
def test_recent_or_site_managed_browser_does_not_enqueue(
    clocked_queue, monkeypatch, template
):
    monkeypatch.setattr(scheduling, "get_template", lambda name: template)
    scheduling.schedule_camera_capture("dashboard", {}, 120)
    assert queue.health()["pending"] == 0


def test_native_camera_schedule_is_unchanged(clocked_queue, monkeypatch):
    template = fresh(browser=False)
    monkeypatch.setattr(scheduling, "get_template", lambda name: template)
    worker = Mock()
    monkeypatch.setattr(scheduling, "run_with_timeout", worker)
    scheduling.schedule_camera_capture("camera", {}, 120)
    worker.assert_called_once_with(scheduling.update_camera, ("camera", template), 120)
