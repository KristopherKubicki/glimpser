import unittest
from unittest.mock import patch

from app.config import _ffmpeg_supports_hwaccel, _machine_supports_hwaccel


class TestMachineSupportsHWAccel(unittest.TestCase):
    def test_true_when_device_exists(self):
        with (
            patch("app.config.os.path.exists", return_value=True),
            patch("app.config.shutil.which", return_value=None),
        ):
            self.assertTrue(_machine_supports_hwaccel())

    def test_true_when_nvidia_smi_found(self):
        with (
            patch("app.config.os.path.exists", return_value=False),
            patch("app.config.shutil.which", return_value="/usr/bin/nvidia-smi"),
        ):
            self.assertTrue(_machine_supports_hwaccel())

    def test_false_when_no_gpu(self):
        with (
            patch("app.config.os.path.exists", return_value=False),
            patch("app.config.shutil.which", return_value=None),
        ):
            self.assertFalse(_machine_supports_hwaccel())


class TestFFmpegSupportsHWAccel(unittest.TestCase):
    def test_returns_true_with_methods(self):
        output = b"Hardware acceleration methods:\nvaapi"
        with patch("app.config.subprocess.check_output", return_value=output):
            self.assertTrue(_ffmpeg_supports_hwaccel())

    def test_returns_false_on_error(self):
        with patch("app.config.subprocess.check_output", side_effect=Exception("fail")):
            self.assertFalse(_ffmpeg_supports_hwaccel())


if __name__ == "__main__":
    unittest.main()
