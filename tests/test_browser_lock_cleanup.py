"""Failed lock acquisition must not hold browser capacity via traceback locals."""

import fcntl
from unittest.mock import Mock

import pytest

from app.utils import screenshots as ss


@pytest.mark.parametrize("operation", ["write", "flush"])
def test_metadata_failure_closes_real_lock_even_with_retained_traceback(
    tmp_path, monkeypatch, operation
):
    path = tmp_path / "browser.lock"
    handle = path.open("a+")
    wrapper = Mock(wraps=handle)
    getattr(wrapper, operation).side_effect = OSError("disk full")
    monkeypatch.setattr(ss, "open", lambda *args, **kwargs: wrapper, raising=False)
    monkeypatch.setenv("GLIMPSER_BROWSER_CAPTURE_LOCK", str(path))
    try:
        with pytest.raises(OSError, match="disk full") as retained:
            ss._acquire_browser_capture_file_lock("camera", 0)
        assert retained.traceback
        assert handle.closed
        with path.open("a+") as contender:
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        handle.close()


def test_busy_wait_sleeps_only_remaining_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_BROWSER_CAPTURE_LOCK", str(tmp_path / "lock"))
    monkeypatch.setattr(ss.fcntl, "flock", Mock(side_effect=BlockingIOError()))
    times = iter([10.0, 10.0, 10.1])
    monkeypatch.setattr(ss.time, "monotonic", lambda: next(times))
    sleeps = []
    monkeypatch.setattr(ss.time, "sleep", sleeps.append)
    assert ss._acquire_browser_capture_file_lock("camera", 0.1) == (False, None)
    assert sleeps == [pytest.approx(0.1)]


def test_interrupted_wait_closes_descriptor(tmp_path, monkeypatch):
    handle = (tmp_path / "lock").open("a+")
    monkeypatch.setattr(ss, "open", lambda *args, **kwargs: handle, raising=False)
    monkeypatch.setattr(ss.fcntl, "flock", Mock(side_effect=BlockingIOError()))
    monkeypatch.setattr(ss.time, "sleep", Mock(side_effect=KeyboardInterrupt()))
    try:
        with pytest.raises(KeyboardInterrupt):
            ss._acquire_browser_capture_file_lock("camera", 1)
        assert handle.closed
    finally:
        handle.close()
