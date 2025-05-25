import unittest
import tempfile
import os
import shutil
from unittest.mock import patch

from app.utils import video_compressor


class TestVideoCompressor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.temp_dir, "cam1"))
        self.raw_file = os.path.join(self.temp_dir, "cam1", "final_1.mp4")
        with open(self.raw_file, "wb") as f:
            f.write(b"0" * 10)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("app.utils.video_compressor.subprocess.run")
    def test_compress_invokes_ffmpeg(self, mock_run):
        with patch("app.utils.video_compressor.VIDEO_DIRECTORY", self.temp_dir), patch(
            "app.utils.video_compressor.MAX_RAW_DATA_SIZE", 1000
        ):
            video_compressor.compress_and_cleanup()
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args[0][0]
        self.assertIn(self.raw_file, cmd)

    @patch("app.utils.video_compressor.subprocess.run")
    def test_raw_deleted_when_limit_exceeded(self, mock_run):
        with patch("app.utils.video_compressor.VIDEO_DIRECTORY", self.temp_dir), patch(
            "app.utils.video_compressor.MAX_RAW_DATA_SIZE", 1
        ):
            video_compressor.compress_and_cleanup()
        self.assertFalse(os.path.exists(self.raw_file))


if __name__ == "__main__":
    unittest.main()
