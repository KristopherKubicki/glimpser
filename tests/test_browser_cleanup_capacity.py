"""Browser cleanup must not reserve capacity for an already exited service."""

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from app.utils import screenshots as ss


def test_exited_service_never_sleeps_or_looks_up_reusable_pid(monkeypatch):
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=5)
    sleep = Mock(side_effect=AssertionError("unnecessary cleanup delay"))
    lookup = Mock(side_effect=AssertionError("PID may have been reused"))
    monkeypatch.setattr(ss.time, "sleep", sleep)
    monkeypatch.setattr(ss.psutil, "Process", lookup)
    ss._driver_local.driver = object()
    ss.kill_driver_process(SimpleNamespace(service=SimpleNamespace(process=process)))
    assert ss._driver_local.driver is None
    sleep.assert_not_called()
    lookup.assert_not_called()


def test_still_running_owned_service_is_terminated(monkeypatch):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    monkeypatch.setattr(
        ss.time, "sleep", Mock(side_effect=AssertionError("fixed delay"))
    )
    try:
        ss.kill_driver_process(
            SimpleNamespace(service=SimpleNamespace(process=process))
        )
        process.wait(timeout=5)
        assert process.returncode is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_failed_launch_without_service_is_safe():
    ss.kill_driver_process(SimpleNamespace(service=None))


def test_stubborn_child_does_not_abandon_siblings_or_root(monkeypatch):
    first, sibling, root = Mock(), Mock(), Mock()
    root.children.return_value = [first, sibling]
    process = Mock(pid=123)
    process.poll.return_value = None
    monkeypatch.setattr(ss.psutil, "Process", Mock(return_value=root))

    def wait(targets, timeout):
        if timeout == 3:
            assert targets == [first, sibling, root]
            for target in targets:
                target.terminate.assert_called_once_with()
            return [sibling, root], [first]
        assert timeout == 2
        assert targets == [first]
        first.kill.assert_called_once_with()
        return [first], []

    waiter = Mock(side_effect=wait)
    monkeypatch.setattr(ss.psutil, "wait_procs", waiter)
    ss.kill_driver_process(SimpleNamespace(service=SimpleNamespace(process=process)))
    assert waiter.call_count == 2
    sibling.kill.assert_not_called()
    root.kill.assert_not_called()


def test_disappearing_child_does_not_skip_remaining_cleanup(monkeypatch):
    vanished, sibling, root = Mock(), Mock(), Mock()
    vanished.terminate.side_effect = ss.psutil.NoSuchProcess(123)
    root.children.return_value = [vanished, sibling]
    process = Mock(pid=321)
    process.poll.return_value = None
    monkeypatch.setattr(ss.psutil, "Process", Mock(return_value=root))
    waiter = Mock(return_value=([vanished, sibling, root], []))
    monkeypatch.setattr(ss.psutil, "wait_procs", waiter)
    ss.kill_driver_process(SimpleNamespace(service=SimpleNamespace(process=process)))
    sibling.terminate.assert_called_once_with()
    root.terminate.assert_called_once_with()
    waiter.assert_called_once_with([vanished, sibling, root], timeout=3)
