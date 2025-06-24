import os
import unittest
from unittest.mock import patch

from app.utils import ffmpeg_setup


class TestFFmpegSetup(unittest.TestCase):
    @patch("app.utils.ffmpeg_setup.subprocess.check_call")
    @patch("app.utils.ffmpeg_setup.Path.exists", return_value=True)
    def test_existing_binary_validates(self, mock_exists, mock_call):
        path = ffmpeg_setup.get_ffmpeg_path()
        self.assertTrue(path.endswith("bin/ffmpeg"))
        mock_call.assert_called_once()

    @patch("app.utils.ffmpeg_setup.subprocess.check_call")
    @patch("app.utils.ffmpeg_setup.Path.exists", return_value=False)
    def test_no_build_when_disabled(self, mock_exists, mock_call):
        with patch.dict(os.environ, {"GLIMPSER_AUTO_BUILD_FFMPEG": "0"}):
            res = ffmpeg_setup.get_ffmpeg_path()
        self.assertIsNone(res)
        mock_call.assert_not_called()

    @patch(
        "app.utils.ffmpeg_setup.subprocess.check_call", side_effect=Exception("fail")
    )
    @patch("app.utils.ffmpeg_setup.Path.exists", side_effect=[False, True])
    def test_build_failure_returns_none(self, mock_exists, mock_call):
        with patch.dict(os.environ, {"GLIMPSER_AUTO_BUILD_FFMPEG": "1"}):
            res = ffmpeg_setup.get_ffmpeg_path()
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
