import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.video_archiver import compile_to_video, archive_screenshots, concatenate_videos, get_video_duration

class TestVideoArchiver(unittest.TestCase):

    @patch('app.utils.video_archiver.subprocess.run')
    def test_compile_to_video(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        result = compile_to_video("/test/camera_path", "/test/video_path")

        self.assertTrue(result)
        mock_run.assert_called()

    @patch('app.utils.video_archiver.os.listdir')
    @patch('app.utils.video_archiver.compile_to_video')
    def test_archive_screenshots(self, mock_compile, mock_listdir):
        mock_listdir.return_value = ["camera1", "camera2"]
        mock_compile.return_value = True

        archive_screenshots()

        self.assertEqual(mock_compile.call_count, 2)

    @patch('app.utils.video_archiver.subprocess.run')
    def test_concatenate_videos(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        result = concatenate_videos("/test/in_process.mp4", "/test/temp.mp4", "/test/video_path")

        self.assertTrue(result)
        mock_run.assert_called()

    @patch('app.utils.video_archiver.subprocess.run')
    def test_get_video_duration(self, mock_run):
        mock_run.return_value = MagicMock(stdout="10.5")

        duration = get_video_duration("/test/video.mp4")

        self.assertEqual(duration, 10.5)
        mock_run.assert_called()

if __name__ == '__main__':
    unittest.main()
