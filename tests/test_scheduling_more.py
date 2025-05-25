import time
import os
import multiprocessing
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import scheduling
from app.utils.scheduling import (
    run_with_timeout,
    add_motion_and_caption,
    get_system_metrics,
)


class TestRunWithTimeout(unittest.TestCase):
    def test_run_completes_before_timeout(self):
        manager = multiprocessing.Manager()
        d = manager.dict()

        def quick(val):
            val["done"] = True

        run_with_timeout(quick, args=(d,), timeout=2)
        self.assertTrue(d.get("done"))

    def test_run_terminated_on_timeout(self):
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
    def test_metrics_fields(self, mock_psutil):
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


if __name__ == "__main__":
    unittest.main()
