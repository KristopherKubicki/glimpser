import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.video_compressor import compress_and_cleanup

class TestVideoCompressor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.temp_dir, "test.mp4")
        with open(self.video_path, "wb") as f:
            f.write(b"dummy")
        self.compressed = self.video_path.replace(".mp4", ".compressed.mp4")

    def tearDown(self):
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.temp_dir)

    @patch("app.utils.video_compressor.MAX_RAW_DATA_SIZE", 10**9)
    def test_compress_and_cleanup(self):
        def side_effect(*args, **kwargs):
            open(self.compressed, "wb").write(b"c")
        with patch("app.utils.video_compressor.VIDEO_DIRECTORY", self.temp_dir), \
             patch("subprocess.run", side_effect=side_effect) as mock_run:
            compress_and_cleanup()
            mock_run.assert_called()
        self.assertTrue(os.path.exists(self.compressed))
        self.assertFalse(os.path.exists(self.video_path))

if __name__ == "__main__":
    unittest.main()
