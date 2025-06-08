import time
import os
import multiprocessing
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import json
from PIL import Image
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import scheduling
from app.utils.scheduling import (
    run_with_timeout,
    add_motion_and_caption,
    get_system_metrics,
    process_offline_jobs,
)


dummy_log = []


def dummy_job(arg):
    """Helper function for offline job tests."""
    dummy_log.append(arg)


class TestRunWithTimeout(unittest.TestCase):
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_completes_before_timeout(self, _online):
        manager = multiprocessing.Manager()
        d = manager.dict()

        def quick(val):
            val["done"] = True

        run_with_timeout(quick, args=(d,), timeout=2)
        self.assertTrue(d.get("done"))

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_terminated_on_timeout(self, _online):
        manager = multiprocessing.Manager()
        d = manager.dict()

        def slow(val):
            time.sleep(1)
            val["done"] = True

        run_with_timeout(slow, args=(d,), timeout=0.2)
        self.assertIsNone(d.get("done"))


class TestAddMotionAndCaption(unittest.TestCase):
    def test_image_updated_with_caption_and_motion(self):
        with unittest.mock.patch("app.utils.scheduling.DEBUG", False):
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "test.png")
                Image.new("RGB", (50, 50), color="white").save(path)
                original = open(path, "rb").read()
                add_motion_and_caption(path, caption="hi", motion=True)
                updated = open(path, "rb").read()
                self.assertNotEqual(original, updated)
                Image.open(path).verify()


class TestGetSystemMetrics(unittest.TestCase):
    @patch("app.utils.scheduling.psutil")
    @patch("app.utils.scheduling.ffmpeg_version", return_value="6.0")
    @patch("app.utils.scheduling.machine_supports_hwaccel", return_value=True)
    @patch("app.utils.scheduling.ffmpeg_supports_hwaccel", return_value=True)
    @patch.object(scheduling, "FFMPEG_HWACCEL", "cuda")
    def test_metrics_fields(
        self,
        mock_ffmpeg_hwaccel,
        mock_machine,
        mock_version,
        mock_psutil,
    ):
        scheduling.system_metrics.update(
            {
                "cpu_usage": 1.234,
                "memory_usage": 2.345,
                "thread_count": 5,
                "start_time": time.time() - 3661,
            }
        )
        mock_psutil.disk_usage.return_value = SimpleNamespace(percent=55.5)
        mock_psutil.Process.return_value.open_files.return_value = [1, 2, 3]
        metrics = get_system_metrics()
        self.assertEqual(metrics["cpu_usage"], 1.2)
        self.assertEqual(metrics["memory_usage"], 2.3)
        self.assertEqual(metrics["disk_usage"], 55.5)
        self.assertEqual(metrics["open_files"], 3)
        self.assertEqual(metrics["thread_count"], 5)
        self.assertTrue(metrics["uptime"].startswith("1h 1m"))
        self.assertEqual(metrics["ffmpeg_version"], "6.0")
        self.assertTrue(metrics["machine_hwaccel"])
        self.assertTrue(metrics["ffmpeg_hwaccel"])
        self.assertTrue(metrics["hwaccel_enabled"])


class TestOfflineJobQueue(unittest.TestCase):
    @patch("app.utils.scheduling.multiprocessing.Process")
    @patch("app.utils.scheduling.SessionLocal")
    @patch("app.utils.scheduling.is_system_online", return_value=False)
    def test_queue_created_when_offline(
        self, _online, mock_session_local, mock_process
    ):
        class DummySession:
            def __init__(self):
                self.added = []
                self.committed = False

            def add(self, obj):
                self.added.append(obj)

            def commit(self):
                self.committed = True

            def rollback(self):
                pass

            def close(self):
                pass

        session = DummySession()
        mock_session_local.return_value = session

        run_with_timeout(lambda: None, timeout=1)

        self.assertEqual(len(session.added), 1)
        self.assertTrue(session.committed)
        mock_process.assert_not_called()

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    @patch("app.utils.scheduling.SessionLocal")
    def test_process_runs_and_clears_jobs(self, mock_session_local, _online):
        class DummyQuery:
            def __init__(self, session):
                self.session = session

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return list(self.session.jobs)

        class DummySession:
            def __init__(self, jobs):
                self.jobs = jobs
                self.deleted = []

            def query(self, model):
                return DummyQuery(self)

            def delete(self, obj):
                self.deleted.append(obj)
                self.jobs.remove(obj)

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        job = scheduling.OfflineJob(
            function="tests.test_scheduling_more.dummy_job",
            args=json.dumps(["ok"]),
            timeout=1,
            timestamp=0,
        )
        session = DummySession([job])
        mock_session_local.return_value = session

        with patch("app.utils.scheduling.run_with_timeout") as mock_run:
            process_offline_jobs()

        mock_run.assert_called_once()
        self.assertIn(job, session.deleted)


if __name__ == "__main__":
    unittest.main()
