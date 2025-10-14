import datetime
import threading
import time
from collections import deque
from unittest.mock import MagicMock, patch

from app.utils import scheduling, system_metrics


class DummyFile:
    def __init__(self, lines=None):
        self.lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def readline(self):
        return self.lines.pop(0) if self.lines else ""

    def seek(self, *args):
        pass

    def close(self):
        pass


def test_cache_logs_parses_lines(tmp_path):
    event = threading.Event()
    new_cache = deque(maxlen=10000)

    def fake_open(path, mode="r", *args, **kwargs):
        if "r" in mode:
            return DummyFile(
                [
                    "2024-01-01 00:00:00,000 - INFO - system - start\n",
                    "2024-01-01 00:00:01,000 - ERROR - camera - fail\n",
                    "",
                ]
            )
        return DummyFile()

    with (
        patch.object(scheduling, "LOGGING_PATH", str(tmp_path / "test.log")),
        patch.object(system_metrics, "stop_event", event),
        patch.object(system_metrics, "log_cache", new_cache),
        patch("builtins.open", fake_open),
        patch("os.makedirs"),
        patch("app.utils.scheduling.time.sleep", lambda _: None),
    ):
        t = threading.Thread(target=scheduling.cache_logs, daemon=True)
        t.start()
        time.sleep(0.01)
        event.set()
        t.join(timeout=1)

    with scheduling.log_cache_lock:
        entries = list(new_cache)

    assert len(entries) == 2
    assert entries[0]["level"] == "INFO"
    assert entries[1]["level"] == "ERROR"
    assert entries[1]["source"] == "camera"
    assert entries[1]["message"] == "fail"
    for e in entries:
        assert isinstance(e["timestamp"], datetime.datetime)


def test_start_and_stop_log_caching():
    event = threading.Event()
    thread_instance = MagicMock()
    with (
        patch(
            "app.utils.scheduling.threading.Thread", return_value=thread_instance
        ) as mock_thread,
        patch.object(system_metrics, "stop_event", event),
        patch.object(system_metrics, "metrics_thread", None),
        patch.object(system_metrics, "log_caching_thread", None),
    ):
        scheduling.start_log_caching()
        mock_thread.assert_called_once_with(target=scheduling.cache_logs, daemon=True)
        thread_instance.start.assert_called_once()

        scheduling.stop_background_tasks()
        assert event.is_set()
        thread_instance.join.assert_called_once_with(timeout=1)
