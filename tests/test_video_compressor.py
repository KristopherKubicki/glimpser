import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import shutil
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.utils.video_compressor as vc


class TestVideoCompressor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.screenshot_dir = os.path.join(self.temp_dir, "screenshots")
        self.video_dir = os.path.join(self.temp_dir, "videos")
        os.makedirs(self.screenshot_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)
        self.camera_dir = os.path.join(self.screenshot_dir, "cam1")
        os.makedirs(self.camera_dir, exist_ok=True)
        with open(os.path.join(self.camera_dir, "frame1.png"), "wb") as f:
            f.write(b"x" * 10)
        with open(os.path.join(self.camera_dir, "frame2.png"), "wb") as f:
            f.write(b"x" * 10)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("app.utils.video_compressor.subprocess.run")
    def test_ffmpeg_invocation(self, mock_run):
        with patch.object(vc, "SCREENSHOT_DIRECTORY", self.screenshot_dir), \
             patch.object(vc, "VIDEO_DIRECTORY", self.video_dir), \
             patch.object(vc, "MAX_RAW_DATA_SIZE", 10 ** 6), \
             patch.object(vc, "FFMPEG_PATH", "ffmpeg"), \
             patch.object(vc, "FFMPEG_HWACCEL", "False"):
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            vc.compress_and_cleanup()

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], "ffmpeg")
            self.assertIn(os.path.join(self.camera_dir, "*.png"), cmd)
            self.assertIn(
                os.path.join(self.video_dir, "cam1", "cam1.mp4"), cmd
            )

    @patch("app.utils.video_compressor.subprocess.run")
    def test_cleanup_when_size_exceeded(self, mock_run):
        with patch.object(vc, "SCREENSHOT_DIRECTORY", self.screenshot_dir), \
             patch.object(vc, "VIDEO_DIRECTORY", self.video_dir), \
             patch.object(vc, "MAX_RAW_DATA_SIZE", 1), \
             patch.object(vc, "FFMPEG_PATH", "ffmpeg"), \
             patch.object(vc, "FFMPEG_HWACCEL", "False"):
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            vc.compress_and_cleanup()

            self.assertEqual(os.listdir(self.camera_dir), [])


if __name__ == "__main__":
    unittest.main()
