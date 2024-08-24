import unittest
import os
import sys
import tempfile
from unittest.mock import patch

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
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.temp_dir)

    def test_validate_template_name(self):
        self.assertEqual(validate_template_name("valid_name"), "valid_name")
        self.assertEqual(validate_template_name("valid-name.123"), "valid-name.123")
        self.assertIsNone(validate_template_name("invalid name"))
        self.assertIsNone(validate_template_name("invalid/name"))
        self.assertIsNone(validate_template_name("-invalid"))
        self.assertIsNone(validate_template_name("invalid-"))
        self.assertIsNone(validate_template_name("a" * 33))  # Too long
        self.assertIsNone(validate_template_name(""))  # Empty string

    def test_touch(self):
        test_file = os.path.join(self.temp_dir, "test_file.txt")
        touch(test_file)
        self.assertTrue(os.path.exists(test_file))

    def test_trim_group_name(self):
        self.assertEqual(trim_group_name("Test Group"), "test_group")
        self.assertEqual(trim_group_name("NoSpaces"), "nospaces")
        self.assertEqual(trim_group_name("Multiple   Spaces"), "multiple___spaces")

    @patch("app.utils.video_archiver.get_templates")
    @patch("app.utils.video_archiver.get_video_duration")
    @patch("app.utils.video_archiver.compile_videos")
    def test_compile_to_teaser(
        self, mock_compile_videos, mock_get_video_duration, mock_get_templates
    ):
        mock_get_templates.return_value = {
            "camera1": {"groups": "group1,group2"},
            "camera2": {"groups": "group2,group3"},
        }
        mock_get_video_duration.return_value = 10

        with patch("os.path.exists", return_value=True), patch(
            "glob.glob", return_value=["/path/to/video.mp4"]
        ):
            compile_to_teaser()

        self.assertTrue(mock_compile_videos.called)
        # Add more assertions based on the expected behavior

    @patch("subprocess.run")
    def test_compile_videos(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        with tempfile.NamedTemporaryFile(mode="w+") as temp_file:
            temp_file.write("dummy content")
            temp_file.flush()
            result = compile_videos(temp_file.name, "output.mp4")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_get_video_duration(self, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "10.5"
        duration = get_video_duration("dummy.mp4")
        self.assertEqual(duration, 10.5)

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("subprocess.run")
    def test_concatenate_videos(self, mock_subprocess_run, mock_get_video_duration):
        mock_get_video_duration.return_value = 10
        mock_subprocess_run.return_value.returncode = 0
        result = concatenate_videos("in_process.mp4", "temp.mp4", self.temp_dir)
        self.assertTrue(result)

    def test_handle_concat_error(self):
        with patch("os.path.getsize", return_value=100), patch(
            "os.rename"
        ) as mock_rename:
            handle_concat_error(
                Exception("Invalid data found"), "temp.mp4", "in_process.mp4"
            )
            mock_rename.assert_called_once_with("temp.mp4", "in_process.mp4")

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("app.utils.video_archiver.concatenate_videos")
    @patch("glob.glob")
    def test_compile_to_video(
        self, mock_glob, mock_concatenate_videos, mock_get_video_duration
    ):
        mock_glob.return_value = ["frame1.png", "frame2.png"]
        mock_get_video_duration.return_value = 5
        mock_concatenate_videos.return_value = True

        with patch("os.path.exists", return_value=True), patch(
            "os.path.getsize", return_value=1000
        ), patch("subprocess.run") as mock_subprocess_run:
            mock_subprocess_run.return_value.returncode = 0
            result = compile_to_video(self.temp_dir, self.temp_dir)

        self.assertTrue(result)

    @patch("app.utils.video_archiver.compile_to_video")
    def test_archive_screenshots(self, mock_compile_to_video):
        with patch("os.listdir", return_value=["camera1", "camera2"]), patch(
            "os.path.isdir", return_value=True
        ):
            archive_screenshots()
        self.assertEqual(mock_compile_to_video.call_count, 2)


if __name__ == "__main__":
    unittest.main()
