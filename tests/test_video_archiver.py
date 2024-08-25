import unittest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.video_archiver import (
    validate_template_name,
    touch,
    trim_group_name,
    compile_to_teaser,
    compile_videos,
    get_video_duration,
    concatenate_videos,
    handle_concat_error,
    compile_to_video,
    archive_screenshots,
)

class TestVideoArchiver(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    @patch('subprocess.run')
    def test_compile_videos(self, mock_run):
        input_file = os.path.join(self.temp_dir, 'input.txt')
        output_file = os.path.join(self.temp_dir, 'output.mp4')

        with open(input_file, 'w', encoding='utf-8') as f:
            f.write('dummy content')

        mock_run.return_value = MagicMock(returncode=0)

        result = compile_videos(input_file, output_file)

        self.assertTrue(result)
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_get_video_duration(self, mock_run):
        video_path = os.path.join(self.temp_dir, 'test_video.mp4')
        with open(video_path, 'w', encoding='utf-8') as f:
            f.write('dummy content')

        mock_run.return_value = MagicMock(stdout='10.5')

        duration = get_video_duration(video_path)

        self.assertEqual(duration, 10.5)
        mock_run.assert_called_once()

    @patch('subprocess.run')
    @patch('app.utils.video_archiver.get_video_duration')
    def test_concatenate_videos(self, mock_get_duration, mock_run):
        in_process_video = os.path.join(self.temp_dir, 'in_process.mp4')
        temp_video = os.path.join(self.temp_dir, 'temp.mp4')
        video_path = self.temp_dir

        with open(in_process_video, 'w', encoding='utf-8') as f:
            f.write('dummy content')
        with open(temp_video, 'w', encoding='utf-8') as f:
            f.write('dummy content')

        mock_get_duration.side_effect = [10.0, 5.0]
        mock_run.return_value = MagicMock(returncode=0)

        result = concatenate_videos(in_process_video, temp_video, video_path)

        self.assertTrue(result)
        mock_run.assert_called_once()
        self.assertEqual(mock_get_duration.call_count, 2)

if __name__ == '__main__':
    unittest.main()
