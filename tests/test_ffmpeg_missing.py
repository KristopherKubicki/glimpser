import unittest
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.utils.screenshots as ss


class TestFFmpegMissing(unittest.TestCase):
    def setUp(self):
        ss.FFMPEG_AVAILABLE = None

    def test_ytdlp_returns_false_without_ffmpeg(self):
        with patch("app.utils.screenshots.shutil.which", return_value=None):
            with patch("app.utils.screenshots.subprocess.run") as mock_run:
                res = ss.capture_frame_with_ytdlp("http://example.com", "out.png")
        self.assertFalse(res)
        mock_run.assert_not_called()

    def test_stream_returns_false_without_ffmpeg(self):
        with patch("app.utils.screenshots.shutil.which", return_value=None):
            with patch("app.utils.screenshots.subprocess.run") as mock_run:
                with (
                    patch("app.utils.screenshots.os.makedirs"),
                    patch("app.utils.screenshots.os.path.exists", return_value=False),
                ):
                    res = ss.capture_frame_from_stream("http://example.com", "out.png")
        self.assertFalse(res)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
