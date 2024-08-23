import unittest
import os
import sys
from unittest.mock import patch
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import video_archiver


class TestVideoArchiver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Clean up the temporary directory
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.temp_dir)

    def test_validate_template_name(self):
        self.assertTrue(video_archiver.validate_template_name("valid_template"))
        self.assertFalse(video_archiver.validate_template_name("invalid/template"))
        self.assertFalse(video_archiver.validate_template_name("invalid..template"))
        self.assertFalse(video_archiver.validate_template_name("a" * 33))  # Too long
        self.assertFalse(video_archiver.validate_template_name(None))
        self.assertFalse(video_archiver.validate_template_name(123))  # Not a string

    def test_trim_group_name(self):
        self.assertEqual(video_archiver.trim_group_name("Test Group"), "test_group")
        self.assertEqual(video_archiver.trim_group_name("NoSpaces"), "nospaces")
        self.assertEqual(
            video_archiver.trim_group_name("Multiple   Spaces"), "multiple___spaces"
        )

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("app.utils.video_archiver.get_templates")
    @patch("app.utils.video_archiver.compile_videos")
    def test_compile_to_teaser(
        self, mock_compile_videos, mock_get_templates, mock_get_video_duration
    ):
        # Mock the necessary functions and set up test data
        mock_get_video_duration.return_value = 10
        mock_get_templates.return_value = {
            "camera1": {"groups": "group1,group2"},
            "camera2": {"groups": "group2,group3"},
        }

        # Create some dummy video files
        os.makedirs(os.path.join(self.temp_dir, "camera1"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, "camera2"), exist_ok=True)
        open(os.path.join(self.temp_dir, "camera1", "in_process.mp4"), "w").close()
        open(os.path.join(self.temp_dir, "camera2", "in_process.mp4"), "w").close()

        # Patch the VIDEO_DIRECTORY
        with patch("app.utils.video_archiver.VIDEO_DIRECTORY", self.temp_dir):
            video_archiver.compile_to_teaser()

        # Check if compile_videos was called with the correct arguments
        self.assertEqual(
            mock_compile_videos.call_count, 3
        )  # Once for all cameras, twice for groups

    @patch("subprocess.run")
    def test_compile_videos(self, mock_subprocess_run):
        input_file = os.path.join(self.temp_dir, "input.txt")
        output_file = os.path.join(self.temp_dir, "output.mp4")

        # Create a dummy input file
        with open(input_file, "w") as f:
            f.write("dummy content")

        # Set up the mock subprocess.run to simulate successful execution
        mock_subprocess_run.return_value.returncode = 0

        # Call the function
        result = video_archiver.compile_videos(input_file, output_file)

        # Check if the function returned True (indicating success)
        self.assertTrue(result)

        # Check if subprocess.run was called with the correct arguments
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args[0][0]
        self.assertIn("ffmpeg", call_args)
        self.assertIn("-i", call_args)
        self.assertIn(input_file, call_args)
        self.assertIn(output_file, call_args)

    @patch("subprocess.run")
    def test_get_video_duration(self, mock_subprocess_run):
        video_path = os.path.join(self.temp_dir, "test_video.mp4")

        # Create a dummy video file
        open(video_path, "w").close()

        # Set up the mock subprocess.run to return a duration
        mock_subprocess_run.return_value.stdout = "10.5"

        # Call the function
        duration = video_archiver.get_video_duration(video_path)

        # Check if the duration is correct
        self.assertEqual(duration, 10.5)

        # Check if subprocess.run was called with the correct arguments
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args[0][0]
        self.assertIn("ffprobe", call_args)
        self.assertIn(video_path, call_args)

    @patch("subprocess.run")
    @patch("os.path.getsize")
    @patch("os.rename")
    def test_concatenate_videos(self, mock_rename, mock_getsize, mock_subprocess_run):
        in_process_video = os.path.join(self.temp_dir, "in_process.mp4")
        temp_video = os.path.join(self.temp_dir, "temp.mp4")
        video_path = self.temp_dir

        # Set up mocks
        mock_getsize.return_value = 1000  # Simulate non-empty files
        mock_subprocess_run.return_value.returncode = 0

        # Call the function
        video_archiver.concatenate_videos(in_process_video, temp_video, video_path)

        # Check if subprocess.run was called (ffmpeg execution)
        mock_subprocess_run.assert_called_once()

        # Check if os.rename was called to rename the concatenated video
        mock_rename.assert_called()

    def test_handle_concat_error(self):
        temp_video = os.path.join(self.temp_dir, "temp.mp4")
        in_process_video = os.path.join(self.temp_dir, "in_process.mp4")

        # Create dummy files
        open(temp_video, "w").close()
        open(in_process_video, "w").close()

        # Test handling of invalid data error
        error = Exception("/in_process.mp4: Invalid data found")
        video_archiver.handle_concat_error(error, temp_video, in_process_video)

        # Check if temp_video was renamed to in_process_video
        self.assertFalse(os.path.exists(temp_video))
        self.assertTrue(os.path.exists(in_process_video))

    @patch("app.utils.video_archiver.compile_to_video")
    def test_archive_screenshots(self, mock_compile_to_video):
        # Create dummy directories
        os.makedirs(os.path.join(self.temp_dir, "camera1"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, "camera2"), exist_ok=True)

        # Patch the SCREENSHOT_DIRECTORY and VIDEO_DIRECTORY
        with patch(
            "app.utils.video_archiver.SCREENSHOT_DIRECTORY", self.temp_dir
        ), patch("app.utils.video_archiver.VIDEO_DIRECTORY", self.temp_dir):
            video_archiver.archive_screenshots()

        # Check if compile_to_video was called for each camera
        self.assertEqual(mock_compile_to_video.call_count, 2)


if __name__ == "__main__":
    unittest.main()
