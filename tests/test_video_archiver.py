import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import VIDEO_DIRECTORY
from app.utils.validators import validate_template_name
from app.utils.video_archiver import (
    ConcatStatus,
    archive_screenshots,
    compile_to_teaser,
    compile_to_video,
    compile_videos,
    concatenate_videos,
    get_video_duration,
    handle_concat_error,
    run_ffmpeg,
    touch,
    trim_group_name,
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
    def test_compile_to_teaser(self, mock_compile_videos, mock_get_video_duration, mock_get_templates):
        mock_get_templates.return_value = {
            "camera1": {"groups": "group1,group2"},
            "camera2": {"groups": "group2,group3"},
        }
        mock_get_video_duration.return_value = 10

        with (
            patch("os.path.exists", return_value=True),
            patch("glob.glob", return_value=["/path/to/video.mp4"]),
        ):
            compile_to_teaser()

        self.assertTrue(mock_compile_videos.called)
        self.assertEqual(mock_compile_videos.call_count, 4)
        outputs = [c.args[1] for c in mock_compile_videos.call_args_list]
        self.assertIn(os.path.join(VIDEO_DIRECTORY, "all_in_process.mp4"), outputs)
        self.assertIn(os.path.join(VIDEO_DIRECTORY, "group1_in_process.mp4"), outputs)
        self.assertIn(os.path.join(VIDEO_DIRECTORY, "group2_in_process.mp4"), outputs)
        self.assertIn(os.path.join(VIDEO_DIRECTORY, "group3_in_process.mp4"), outputs)

    @patch("subprocess.run")
    def test_compile_videos(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        with tempfile.NamedTemporaryFile(mode="w+") as temp_file:
            temp_file.write("dummy content")
            temp_file.flush()
            with (
                patch("os.path.exists", return_value=True),
                patch("os.path.getsize", return_value=500),
                patch("os.rename"),
            ):
                result = compile_videos(temp_file.name, "output.mp4")
        self.assertTrue(result)

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_get_video_duration(self, mock_exists, mock_subprocess_run):
        # Mock the file check to return True
        mock_exists.return_value = True

        # Mock the subprocess run to return the desired duration
        mock_subprocess_run.return_value.stdout = "10.5"

        # Call the function
        duration = get_video_duration("dummy.mp4")

        # Assert the result
        self.assertEqual(duration, 10.5)

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("subprocess.run")
    def test_concatenate_videos(self, mock_subprocess_run, mock_get_video_duration):
        mock_get_video_duration.return_value = 10
        mock_subprocess_run.return_value.returncode = 0
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.symlink"),
            patch("os.unlink"),
            patch("os.path.getmtime", return_value=100),
            patch("time.time", return_value=105),
        ):
            result = concatenate_videos("in_process.mp4", "temp.mp4", self.temp_dir)
        self.assertTrue(result)

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("subprocess.run")
    def test_concatenate_videos_retry(self, mock_subprocess_run, mock_get_video_duration):
        mock_get_video_duration.return_value = 10
        mock_subprocess_run.side_effect = [
            RuntimeError("Resource temporarily unavailable"),
            None,
        ]
        with (
            patch(
                "app.utils.video_archiver.handle_concat_error",
                return_value=ConcatStatus.RETRY,
            ) as mock_handle,
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1),
            patch("os.rename"),
            patch("os.symlink"),
            patch("os.path.getmtime", return_value=100),
            patch("time.time", return_value=105),
        ):
            result = concatenate_videos("in.mp4", "tmp.mp4", self.temp_dir)
        self.assertEqual(mock_subprocess_run.call_count, 2)

    @patch("app.utils.video_archiver.logging.warning")
    @patch("app.utils.video_archiver.get_video_duration")
    @patch("subprocess.run")
    def test_concatenate_videos_stale_timestamp(self, mock_subprocess_run, mock_get_video_duration, mock_warning):
        mock_get_video_duration.return_value = 10
        mock_subprocess_run.return_value.returncode = 0
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.symlink"),
            patch("os.unlink"),
            patch("os.path.getmtime", return_value=0),
            patch("time.time", return_value=100),
        ):
            result = concatenate_videos("in.mp4", "tmp.mp4", self.temp_dir)

        self.assertFalse(result)
        mock_warning.assert_called_once()

    def test_handle_concat_error(self):
        with (
            patch("os.path.getsize", return_value=100),
            patch("os.rename") as mock_rename,
        ):
            status = handle_concat_error(Exception("Invalid data found"), "temp.mp4", "in_process.mp4")
            mock_rename.assert_called_once_with("temp.mp4", "in_process.mp4")
            self.assertEqual(status, ConcatStatus.RECOVERED)

        with (
            patch("os.path.getsize", return_value=100),
            patch("os.rename") as mock_rename,
        ):
            status = handle_concat_error(
                Exception("Resource temporarily unavailable"),
                "temp.mp4",
                "in_process.mp4",
            )
            mock_rename.assert_not_called()
            self.assertEqual(status, ConcatStatus.RETRY)

        with (
            patch("os.path.getsize", return_value=100),
            patch("os.rename") as mock_rename,
        ):
            status = handle_concat_error(Exception("Some fatal error"), "temp.mp4", "in_process.mp4")
            mock_rename.assert_called_once_with("temp.mp4", "in_process.mp4")
            self.assertEqual(status, ConcatStatus.FATAL)

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("app.utils.video_archiver.concatenate_videos")
    @patch("app.utils.video_archiver.Image.open")
    @patch("app.utils.video_archiver.is_mostly_blank", return_value=False)
    @patch("glob.glob")
    def test_compile_to_video(
        self,
        mock_glob,
        mock_blank,
        mock_open,
        mock_concatenate_videos,
        mock_get_video_duration,
    ):
        mock_glob.return_value = ["frame_2.png", "frame_2.png"]
        mock_get_video_duration.return_value = 5
        mock_concatenate_videos.return_value = True

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=False),
            patch("os.path.getmtime", return_value=1724516114),
            patch("os.path.getctime", return_value=1724516115),
            patch("os.path.getsize", return_value=1000),
            patch("os.rename"),
            patch("app.utils.video_archiver.run_ffmpeg") as mock_run_ffmpeg,
        ):
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_open.return_value.__exit__.return_value = None
            mock_run_ffmpeg.return_value.returncode = 0
            result = compile_to_video(self.temp_dir, self.temp_dir)

        self.assertIsNone(result)
        self.assertTrue(mock_run_ffmpeg.called)

    @patch("app.utils.video_archiver.pipe_ffmpeg_frames")
    @patch("app.utils.video_archiver.Image.open")
    @patch("glob.glob")
    def test_compile_to_video_ignores_blank_frames(self, mock_glob, mock_open, mock_pipe):
        mock_glob.return_value = ["shot_blank.png", "shot_2.png"]

        captured_lines = []

        def fake_pipe(cmd, files):
            captured_lines.extend(files)

            class R:
                returncode = 0

            return R()

        mock_pipe.side_effect = fake_pipe

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=False),
            patch("os.path.getmtime", return_value=1724516114),
            patch("os.path.getctime", return_value=1724516115),
            patch("os.path.getsize", return_value=1000),
            patch("os.rename"),
            patch("app.utils.video_archiver.is_mostly_blank", return_value=False),
        ):
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_open.return_value.__exit__.return_value = None
            compile_to_video(self.temp_dir, self.temp_dir)

        mock_open.assert_called_once_with("shot_2.png")
        # self.assertEqual(captured_lines, ["shot_2.png"])

    @patch("app.utils.video_archiver.compile_to_video")
    def test_archive_screenshots(self, mock_compile_to_video):
        with (
            patch("os.listdir", return_value=["camera1", "camera2"]),
            patch("os.path.isdir", return_value=True),
        ):
            archive_screenshots()
        self.assertEqual(mock_compile_to_video.call_count, 2)

    @patch("app.utils.video_archiver.logging.exception")
    @patch("app.utils.video_archiver.compile_to_video", side_effect=Exception("fail"))
    def test_archive_screenshots_logs_error(self, mock_compile_to_video, mock_log):
        with (
            patch("os.listdir", return_value=["camera1"]),
            patch("os.path.isdir", return_value=True),
        ):
            archive_screenshots()
        mock_log.assert_called_once()

    @patch("subprocess.run")
    def test_run_ffmpeg_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)
        with self.assertRaises(subprocess.TimeoutExpired):
            run_ffmpeg(["ffmpeg"], timeout=1)


if __name__ == "__main__":
    unittest.main()
