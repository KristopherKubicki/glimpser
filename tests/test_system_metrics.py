"""Tests for system metrics."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.utils import system_metrics


class TestFFmpegSupportCaching(unittest.TestCase):
    def setUp(self):
        system_metrics.FFMPEG_GPU_SUPPORT = None

    def tearDown(self):
        system_metrics.FFMPEG_GPU_SUPPORT = None

    def test_ffmpeg_supports_hwaccel_caches_result(self):
        output = b"Hardware acceleration methods:\nvaapi"
        with patch(
            "app.utils.system_metrics.subprocess.check_output", return_value=output
        ) as mock_check:
            self.assertTrue(system_metrics.ffmpeg_supports_hwaccel())
            self.assertTrue(system_metrics.ffmpeg_supports_hwaccel())
            self.assertEqual(mock_check.call_count, 1)

    @patch("app.utils.system_metrics.FFMPEG_HWACCEL", "cuda")
    @patch("app.utils.system_metrics.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("app.utils.system_metrics.machine_supports_hwaccel", return_value=True)
    @patch.object(system_metrics, "FFMPEG_VERSION", "6.0")
    def test_get_system_metrics_uses_cached_value(self, *_):
        with patch("app.utils.system_metrics.psutil") as mock_psutil:
            mock_psutil.disk_usage.return_value = SimpleNamespace(percent=55.5)
            process = mock_psutil.Process.return_value
            if hasattr(process, "num_fds"):
                process.num_fds.return_value = 3
            else:
                process.open_files.return_value = [1, 2, 3]

            with patch(
                "app.utils.system_metrics.subprocess.check_output",
                return_value=b"Hardware acceleration methods:\nvaapi",
            ) as mock_check:
                system_metrics.FFMPEG_GPU_SUPPORT = None
                metrics1 = system_metrics.get_system_metrics()
                metrics2 = system_metrics.get_system_metrics()
                call_count = mock_check.call_count

        self.assertTrue(metrics1["ffmpeg_hwaccel"])
        self.assertTrue(metrics2["ffmpeg_hwaccel"])
        self.assertEqual(call_count, 1)


if __name__ == "__main__":
    unittest.main()
