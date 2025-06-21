import json
import multiprocessing
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.utils import scheduling
from app.utils.scheduling import (
    add_motion_and_caption,
    get_system_metrics,
    process_offline_jobs,
    run_with_timeout,
)

dummy_log = []


def dummy_job(arg):
    """Helper function for offline job tests."""
    dummy_log.append(arg)


class TestRunWithTimeout(unittest.TestCase):
    def setUp(self):
        scheduling.active_jobs.clear()

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_completes_before_timeout(self, _online):
        with multiprocessing.Manager() as manager:
            d = manager.dict()

            def quick(val):
                val["done"] = True

            run_with_timeout(quick, args=(d,), timeout=2)
            self.assertTrue(d.get("done"))

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_terminated_on_timeout(self, _online):
        with multiprocessing.Manager() as manager:
            d = manager.dict()

            def slow(val):
                time.sleep(1)
                val["done"] = True

            run_with_timeout(slow, args=(d,), timeout=0.2)
            self.assertIsNone(d.get("done"))

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=10)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    @patch("app.utils.scheduling.cas_error")
    @patch("app.utils.scheduling.mark_offline")
    def test_timeout_marks_offline(self, mock_offline, mock_cas_error, _online, _cpu):
        def slow(name, template):
            time.sleep(1)

        run_with_timeout(
            slow,
            args=("cam1", {"url": "http://ex"}),
            timeout=0.2,
        )
        mock_offline.assert_called_once_with("cam1")
        mock_cas_error.assert_called_once_with("http://ex")

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_skip_if_active(self, _online):
        class DummyProc:
            def is_alive(self):
                return True

        scheduling.active_jobs["cam1"] = DummyProc()
        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(lambda name: None, args=("cam1",), timeout=1)
            mock_proc.assert_not_called()

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_backoff_on_failure(self, _online):
        def bad_job():
            raise RuntimeError("boom")

        run_with_timeout(bad_job, timeout=1)
        backoff = scheduling.job_backoff_until.get("bad_job")
        self.assertIsNotNone(backoff)

        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(bad_job, timeout=1)
            mock_proc.assert_not_called()

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=95)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_skip_on_high_cpu(self, _online, _cpu):
        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(lambda: None, timeout=1)
            mock_proc.assert_not_called()

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=10)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_process_title_set(self, _online, _cpu):
        def my_job(name):
            return name

        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(my_job, args=("cam1",), timeout=1)
            mock_proc.assert_called_once()
            _, kwargs = mock_proc.call_args
            self.assertEqual(kwargs["name"], "glimpser my_job:cam1")

        scheduling.job_backoff_until.clear()
        scheduling.job_failures.clear()


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
    @patch.object(scheduling, "FFMPEG_VERSION", "6.0")
    @patch("app.utils.scheduling.machine_supports_hwaccel", return_value=True)
    @patch("app.utils.scheduling.ffmpeg_supports_hwaccel", return_value=True)
    @patch("app.utils.scheduling.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch.object(scheduling, "FFMPEG_HWACCEL", "cuda")
    def test_metrics_fields(
        self,
        mock_which,
        mock_ffmpeg_supports,
        mock_machine,
        mock_psutil,
    ):
        scheduling.system_metrics.update(
            {
                "cpu_usage": 1.234,
                "memory_usage": 2.345,
                "thread_count": 5,
                "top_threads": [{"id": 123, "name": "Thread-1", "cpu": 10.0}],
                "start_time": time.time() - 3661,
            }
        )
        mock_psutil.disk_usage.return_value = SimpleNamespace(percent=55.5)
        process_mock = mock_psutil.Process.return_value
        if hasattr(process_mock, "num_fds"):
            process_mock.num_fds.return_value = 3
        else:
            process_mock.open_files.return_value = [1, 2, 3]
        metrics = get_system_metrics()
        self.assertEqual(metrics["cpu_usage"], 1.2)
        self.assertEqual(metrics["memory_usage"], 2.3)
        self.assertEqual(metrics["disk_usage"], 55.5)
        self.assertEqual(metrics["open_files"], 3)
        self.assertEqual(metrics["thread_count"], 5)
        self.assertTrue(metrics["uptime"].startswith("1h 1m"))
        self.assertEqual(metrics["ffmpeg_version"], "6.0")
        self.assertEqual(metrics["ffmpeg_path"], "/usr/bin/ffmpeg")
        self.assertTrue(metrics["machine_hwaccel"])
        self.assertTrue(metrics["ffmpeg_hwaccel"])
        self.assertTrue(metrics["ffmpeg_gpu_support"])
        self.assertTrue(metrics["hwaccel_enabled"])
        self.assertTrue(metrics["gpu_support"])
        self.assertTrue(metrics["ffmpeg_gpu_enabled"])
        self.assertTrue(metrics["danger_mode"])
        self.assertEqual(
            metrics["top_threads"], [{"id": 123, "name": "Thread-1", "cpu": 10.0}]
        )


class TestOfflineJobQueue(unittest.TestCase):
    def setUp(self):
        scheduling.active_jobs.clear()

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
