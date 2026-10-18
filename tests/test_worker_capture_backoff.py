"""Real subprocess checks: capture failure must survive a normal child return."""

import multiprocessing
from types import SimpleNamespace

import pytest

from app.utils import ptz_views, scheduling


@pytest.fixture
def worker_state(monkeypatch):
    if multiprocessing.get_start_method() != "fork":
        pytest.skip("production fork worker semantics")
    now = [1000.0]
    monkeypatch.setattr(scheduling.time, "time", lambda: now[0])
    monkeypatch.setattr(scheduling, "is_system_online", lambda: True)
    monkeypatch.setattr(scheduling.psutil, "cpu_percent", lambda **kwargs: 0)
    monkeypatch.setattr(
        scheduling.psutil, "virtual_memory", lambda: SimpleNamespace(percent=0)
    )
    monkeypatch.setattr(scheduling, "mark_offline", lambda *args: None)
    for name in (
        "active_jobs",
        "job_failures",
        "job_backoff_until",
        "job_circuit_open_until",
        "job_circuit_next_probe",
        "throttle_cache",
    ):
        monkeypatch.setattr(scheduling, name, {})
    return now


def test_actual_failed_capture_accumulates_and_opens_parent_circuit(
    worker_state, monkeypatch
):
    attempts = multiprocessing.Value("i", 0)

    def fail_capture(*args):
        attempts.value += 1
        return False

    monkeypatch.setattr(ptz_views, "capture", fail_capture)
    monkeypatch.setattr(
        scheduling,
        "get_template",
        lambda name: {"name": name, "url": "http://camera.invalid/frame"},
    )
    monkeypatch.setattr(scheduling, "set_capture_failed", lambda *args: None)
    monkeypatch.setattr(scheduling, "JOB_CIRCUIT_FAILURE_THRESHOLD", 2)
    assert (
        scheduling.run_with_timeout(scheduling.update_camera, ("broken", {}), 5)
        is False
    )
    assert scheduling.job_failures["broken"] == 1
    worker_state[0] += 10
    assert (
        scheduling.run_with_timeout(scheduling.update_camera, ("broken", {}), 5)
        is False
    )
    assert scheduling.job_failures["broken"] == 2
    assert scheduling.job_circuit_open_until["broken"] > worker_state[0]
    worker_state[0] += 10
    assert (
        scheduling.run_with_timeout(scheduling.update_camera, ("broken", {}), 5) is None
    )
    assert attempts.value == 2
    assert scheduling.active_jobs == {}
    worker_state[0] += scheduling.JOB_CIRCUIT_PROBE_SECONDS
    assert scheduling.run_with_timeout(_accepted_capture, ("broken",), 5) is True
    assert "broken" not in scheduling.job_failures
    assert "broken" not in scheduling.job_circuit_open_until


def _busy_capture(name):
    return scheduling.CAPTURE_STALE_BROWSER_SLOT_BUSY


def _accepted_capture(name):
    return {"generic_job_result": True}


def _unchanged_capture(name):
    return "source_checked_unchanged"


@pytest.mark.parametrize("recovery", [_accepted_capture, _unchanged_capture])
def test_stale_capture_preserves_history_and_recovery_clears_it(worker_state, recovery):
    scheduling.job_failures["camera"] = 2
    assert scheduling.run_with_timeout(_busy_capture, ("camera",), 5) is None
    assert scheduling.job_failures["camera"] == 2
    assert scheduling.active_jobs == {}
    assert scheduling.run_with_timeout(recovery, ("camera",), 5) is True
    assert scheduling.job_failures == {}


def _explicit_exit(name):
    raise SystemExit(3)


def test_explicit_error_exit_is_not_a_capture_deferral(worker_state):
    assert scheduling.run_with_timeout(_explicit_exit, ("camera",), 5) is False
    assert scheduling.job_failures["camera"] == 1


def test_browser_wrapper_propagates_busy_result_without_charging_attempt(
    worker_state, monkeypatch, tmp_path
):
    queue = scheduling.browser_queue
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    monkeypatch.setattr(scheduling, "get_template", lambda name: {"name": name})
    monkeypatch.setattr(
        scheduling,
        "update_camera",
        lambda *args: scheduling.CAPTURE_STALE_BROWSER_SLOT_BUSY,
    )
    queue.enqueue("browser", {})
    turn = queue.claim()
    scheduling.job_failures["browser"] = 2
    assert (
        scheduling.run_with_timeout(
            scheduling.retry_browser_camera, (turn["name"], turn["token"]), 5
        )
        is None
    )
    assert scheduling.job_failures["browser"] == 2
    with queue._database() as db:
        row = db.execute(
            "select attempts, lease from turns where name='browser'"
        ).fetchone()
    assert row["attempts"] == row["lease"] == 0
