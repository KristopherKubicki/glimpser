"""Real worker exit and durable local-contention regression tests."""

import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.utils import browser_queue as queue
from app.utils import scheduling


def _successful_job(marker):
    marker.value = 1


def _failed_job(marker):
    marker.value = 1
    raise RuntimeError("intentional test failure")


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(), reason="fork only"
)
@pytest.mark.parametrize("job, expected", [(_successful_job, 0), (_failed_job, 1)])
def test_forked_thread_pool_worker_reports_actual_result(job, expected):
    context = multiprocessing.get_context("fork")
    marker = context.Value("i", 0)

    def run():
        process = context.Process(target=scheduling._run_target, args=(job, (marker,)))
        process.start()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join(5)
            pytest.fail("capture worker failed to exit")
        return process.exitcode

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(run).result(timeout=20) == expected
    assert marker.value == 1


def test_successful_thread_pool_capture_does_not_open_false_circuit(monkeypatch):
    monkeypatch.setattr(scheduling, "is_system_online", lambda: True)
    monkeypatch.setattr(scheduling.psutil, "cpu_percent", lambda **k: 0)
    monkeypatch.setattr(
        scheduling.psutil, "virtual_memory", lambda: SimpleNamespace(percent=0)
    )
    for name in (
        "active_jobs",
        "job_failures",
        "job_backoff_until",
        "job_circuit_open_until",
        "job_circuit_next_probe",
    ):
        monkeypatch.setattr(scheduling, name, {})
    marker = multiprocessing.Value("i", 0)
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert (
            executor.submit(
                scheduling.run_with_timeout, _successful_job, (marker,), 5
            ).result(timeout=15)
            is True
        )
    assert marker.value == 1
    assert scheduling.job_failures == {}
    assert scheduling.job_circuit_open_until == {}


@pytest.fixture
def clocked_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    now = [1000.0]
    monkeypatch.setattr(queue.time, "time", lambda: now[0])
    monkeypatch.setattr(queue.random, "uniform", lambda *a: 0)
    return now


def test_local_contention_does_not_exhaust_source_attempts(clocked_queue):
    queue.enqueue("WiFi", {})
    for _ in range(queue.MAX_ATTEMPTS + 3):
        turn = queue.claim()
        assert turn["name"] == "WiFi"
        queue.finish(**turn, retry=True, attempted=False)
        clocked_queue[0] += 35
    assert queue.health()["pending"] == 1
    assert queue.health()["oldest_wait_seconds"] == 35 * (queue.MAX_ATTEMPTS + 3)
    assert queue.claim()["name"] == "WiFi"


def test_real_failed_attempts_still_have_a_limit(clocked_queue):
    queue.enqueue("bad", {})
    for _ in range(queue.MAX_ATTEMPTS):
        turn = queue.claim()
        assert turn is not None
        queue.finish(**turn, retry=True)
        clocked_queue[0] += 100
    assert queue.health()["pending"] == 0


def test_stale_ack_cannot_modify_new_lease(clocked_queue):
    queue.enqueue("camera", {})
    old = queue.claim()
    clocked_queue[0] += queue.LEASE_SECONDS + 1
    current = queue.claim()
    queue.finish(**old, retry=True, attempted=False)
    assert queue.owns_lease(**current)


def test_scheduler_resource_skip_keeps_ticket(clocked_queue, monkeypatch):
    monkeypatch.setattr(scheduling, "is_system_online", lambda: True)
    monkeypatch.setattr(scheduling, "get_template", lambda name: {"name": name})
    monkeypatch.setattr(scheduling, "run_with_timeout", lambda *a: None)
    queue.enqueue("camera", {})
    for _ in range(queue.MAX_ATTEMPTS + 1):
        scheduling.process_browser_queue()
        clocked_queue[0] += 35
    assert queue.health()["pending"] == 1


def test_admission_samples_current_load_after_expensive_previous_job(monkeypatch):
    monkeypatch.setattr(scheduling, "is_system_online", lambda: True)
    # Model a busy previous capture followed by an idle host: the accumulated
    # per-thread average is high, but a bounded current measurement is low.
    monkeypatch.setattr(
        scheduling.psutil, "cpu_percent", lambda interval: 99 if interval == 0 else 10
    )
    monkeypatch.setattr(
        scheduling.psutil, "virtual_memory", lambda: SimpleNamespace(percent=0)
    )
    for name in (
        "active_jobs",
        "job_failures",
        "job_backoff_until",
        "job_circuit_open_until",
        "job_circuit_next_probe",
    ):
        monkeypatch.setattr(scheduling, name, {})
    marker = multiprocessing.Value("i", 0)
    assert scheduling.run_with_timeout(_successful_job, (marker,), 5) is True
    assert marker.value == 1
