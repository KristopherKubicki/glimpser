import datetime
import os
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from PIL import Image

from app.config import VIDEO_DIRECTORY
from app.utils.validators import validate_template_name
from app.utils.video_archiver import (
    ConcatStatus,
    _build_timelapse_filter,
    _collect_new_frame_files,
    _ffmpeg_command_without_hwaccel,
    _ffmpeg_error_suggests_hwaccel_failure,
    archive_screenshots,
    compile_to_teaser,
    compile_to_video,
    compile_videos,
    concatenate_videos,
    get_video_duration,
    handle_concat_error,
    pipe_ffmpeg_frames,
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
    def test_compile_to_teaser(
        self, mock_compile_videos, mock_get_video_duration, mock_get_templates
    ):
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
            temp_file.write("file 'example.mp4'\n")
            temp_file.flush()
            with (
                patch("os.path.exists", return_value=True),
                patch("os.path.getsize", return_value=500),
                patch("os.rename"),
            ):
                result = compile_videos(temp_file.name, "output.mp4")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_compile_videos_missing_input(self, mock_subprocess_run):
        result = compile_videos("missing.txt", "out.mp4")
        self.assertFalse(result)

    @patch("app.utils.video_archiver.compile_videos")
    def test_compile_to_teaser_no_dir(self, mock_compile):
        with (
            patch("os.path.isdir", return_value=False),
            patch("os.makedirs"),
        ):
            res = compile_to_teaser()
        mock_compile.assert_not_called()
        self.assertFalse(res)

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
    def test_concatenate_videos_retry(
        self, mock_subprocess_run, mock_get_video_duration
    ):
        mock_get_video_duration.return_value = 10
        mock_subprocess_run.side_effect = [
            RuntimeError("Resource temporarily unavailable"),
            None,
        ]
        with (
            patch(
                "app.utils.video_archiver.handle_concat_error",
                return_value=ConcatStatus.RETRY,
            ),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1),
            patch("os.rename"),
            patch("os.symlink"),
            patch("os.path.getmtime", return_value=100),
            patch("time.time", return_value=105),
        ):
            concatenate_videos("in.mp4", "tmp.mp4", self.temp_dir)
        self.assertEqual(mock_subprocess_run.call_count, 2)

    @patch("app.utils.video_archiver.logging.warning")
    @patch("app.utils.video_archiver.get_video_duration")
    @patch("subprocess.run")
    def test_concatenate_videos_stale_timestamp(
        self, mock_subprocess_run, mock_get_video_duration, mock_warning
    ):
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
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=100),
            patch("os.rename") as mock_rename,
        ):
            status = handle_concat_error(
                Exception("Invalid data found"), "temp.mp4", "in_process.mp4"
            )
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
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=100),
            patch("os.rename") as mock_rename,
        ):
            status = handle_concat_error(
                Exception("Some fatal error"), "temp.mp4", "in_process.mp4"
            )
            mock_rename.assert_called_once_with("temp.mp4", "in_process.mp4")
            self.assertEqual(status, ConcatStatus.FATAL)

    @patch("app.utils.video_archiver.get_video_duration")
    @patch("app.utils.video_archiver.concatenate_videos")
    @patch("app.utils.video_archiver.Image.open")
    @patch("app.utils.video_archiver._is_valid_png", return_value=True)
    @patch("app.utils.video_archiver.is_mostly_blank", return_value=False)
    @patch("glob.glob")
    def test_compile_to_video(  # noqa: PLR0913
        self,
        mock_glob,
        mock_blank,
        mock_is_valid,
        mock_open,
        mock_concatenate_videos,
        mock_get_video_duration,
    ):
        camera_name = os.path.basename(self.temp_dir)
        mock_glob.return_value = [
            f"{camera_name}_20260422145530.png",
            f"{camera_name}_20260422150205.png",
            f"{camera_name}_20260422152847.png",
        ]
        mock_get_video_duration.return_value = 5
        mock_concatenate_videos.return_value = True

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=False),
            patch("os.path.getmtime", return_value=1724516114),
            patch("os.path.getctime", return_value=1724516115),
            patch("os.path.getsize", return_value=2048),
            patch("os.rename"),
            patch("app.utils.video_archiver.run_ffmpeg") as mock_run_ffmpeg,
        ):
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_open.return_value.__exit__.return_value = None
            mock_run_ffmpeg.return_value.returncode = 0
            compile_to_video(self.temp_dir, self.temp_dir)

    @patch("app.utils.video_archiver._is_valid_png", return_value=True)
    @patch("app.utils.video_archiver.is_mostly_blank", return_value=False)
    def test_compile_to_video_uses_only_canonical_timestamped_frames(
        self, mock_blank, mock_is_valid
    ):
        camera_path = os.path.join(self.temp_dir, "Front_door_doorbell")
        video_path = os.path.join(self.temp_dir, "video")
        os.makedirs(camera_path, exist_ok=True)
        os.makedirs(video_path, exist_ok=True)

        for name in (
            "Front_door_doorbell_20260422145530.png",
            "Front_door_doorbell_20260422150205.png",
            "Front_door_doorbell_20260422152847.png",
            "Front_door_doorbell_20260422150205.png.orig.png",
            "latest_camera.png",
            "last_motion.png",
            "last_motion_caption.png",
            "prev_motion.png",
        ):
            path = os.path.join(camera_path, name)
            if name.endswith(".orig.png"):
                with open(path, "wb") as handle:
                    handle.write(b"orig")
            else:
                Image.new("RGB", (64, 36), (24, 24, 24)).save(path, format="PNG")

        captured_files = []

        def fake_run_ffmpeg(command, timeout=30):
            concat_path = command[command.index("-i") + 1]
            with open(concat_path, encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("file "):
                        captured_files.append(line.strip().split("'", 2)[1])
            output_path = command[-1]
            with open(output_path, "wb") as handle:
                handle.write(b"0" * 2048)

            class Result:
                returncode = 0

            return Result()

        with (
            patch("app.utils.video_archiver.run_ffmpeg", side_effect=fake_run_ffmpeg),
            patch("app.utils.video_archiver.get_templates", return_value={}),
            patch("app.utils.video_archiver.get_video_duration", return_value=5),
            patch("os.path.getsize", return_value=2048),
        ):
            compile_to_video(camera_path, video_path)

        self.assertEqual(
            [os.path.basename(path) for path in captured_files],
            [
                "Front_door_doorbell_20260422145530.png",
                "Front_door_doorbell_20260422150205.png",
                "Front_door_doorbell_20260422152847.png",
            ],
        )

    @patch("app.utils.video_archiver.is_mostly_blank", return_value=False)
    def test_collect_new_frame_files_uses_filename_timestamps_not_ctime(
        self, mock_blank
    ):
        camera_name = "NewCamera"
        camera_path = os.path.join(self.temp_dir, camera_name)
        os.makedirs(camera_path, exist_ok=True)

        late_old = os.path.join(camera_path, "NewCamera_20260422145530.png")
        newer_one = os.path.join(camera_path, "NewCamera_20260422152847.png")
        newer_two = os.path.join(camera_path, "NewCamera_20260422153026.png")

        for path in (late_old, newer_one, newer_two):
            Image.new("RGB", (128, 128), (24, 48, 72)).save(path, format="PNG")

        cutoff = datetime.datetime(
            2026, 4, 22, 15, 20, tzinfo=datetime.timezone.utc
        ).timestamp()

        with patch(
            "app.utils.video_archiver.os.path.getctime",
            side_effect=AssertionError("ctime should not be consulted"),
        ):
            files = _collect_new_frame_files(camera_path, camera_name, cutoff)

        self.assertEqual(
            [os.path.basename(path) for path in files],
            [
                "NewCamera_20260422152847.png",
                "NewCamera_20260422153026.png",
            ],
        )

    def test_build_timelapse_filter_defaults_to_base_chain(self):
        filt = _build_timelapse_filter("cam1", templates={"cam1": {}})
        self.assertIn("fps=30", filt)
        self.assertNotIn("deflicker=", filt)

    @patch("app.utils.video_archiver.get_templates")
    @patch("app.utils.video_archiver.get_video_duration")
    @patch("app.utils.video_archiver.Image.open")
    @patch("app.utils.video_archiver._is_valid_png", return_value=True)
    @patch("app.utils.video_archiver.is_mostly_blank", return_value=False)
    @patch("glob.glob")
    def test_compile_to_video_includes_deflicker_filter(  # noqa: PLR0913
        self,
        mock_glob,
        mock_blank,
        mock_is_valid,
        mock_open,
        mock_get_video_duration,
        mock_get_templates,
    ):
        camera_path = os.path.join(self.temp_dir, "WhiteGrowerPod")
        os.makedirs(camera_path, exist_ok=True)
        mock_glob.return_value = [
            os.path.join(camera_path, "WhiteGrowerPod_20260422145530.png"),
            os.path.join(camera_path, "WhiteGrowerPod_20260422150205.png"),
            os.path.join(camera_path, "WhiteGrowerPod_20260422152847.png"),
        ]
        # Versioned validation requires real file metadata even when image
        # decoding and FFmpeg are mocked by this command-construction test.
        for frame in mock_glob.return_value:
            with open(frame, "wb") as handle:
                handle.write(b"fixture")
        mock_get_video_duration.return_value = 5
        mock_get_templates.return_value = {
            "WhiteGrowerPod": {"deflicker_mode": "medium"}
        }

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=False),
            patch("os.path.getmtime", return_value=1724516114),
            patch("os.path.getctime", return_value=1724516115),
            patch("os.path.getsize", return_value=2048),
            patch("os.rename"),
            patch("app.utils.video_archiver.run_ffmpeg") as mock_run_ffmpeg,
        ):
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_open.return_value.__exit__.return_value = None
            mock_run_ffmpeg.return_value.returncode = 0
            compile_to_video(camera_path, camera_path)

        command = mock_run_ffmpeg.call_args.args[0]
        vf_index = command.index("-vf") + 1
        self.assertIn("deflicker=s=8:mode=pm", command[vf_index])
        self.assertTrue(mock_run_ffmpeg.called)

    @patch("app.utils.video_archiver.pipe_ffmpeg_frames")
    @patch("app.utils.video_archiver.Image.open")
    @patch("app.utils.video_archiver._is_valid_png", return_value=True)
    @patch("glob.glob")
    def test_compile_to_video_ignores_blank_frames(
        self, mock_glob, mock_is_valid, mock_open, mock_pipe
    ):
        camera_name = os.path.basename(self.temp_dir)
        canonical = os.path.join(self.temp_dir, f"{camera_name}_20260422145530.png")
        with open(canonical, "wb") as handle:
            handle.write(b"fixture")
        mock_glob.return_value = ["shot_blank.png", canonical]

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

        mock_open.assert_called_once_with(canonical)
        # self.assertEqual(captured_lines, ["shot_2.png"])

    @patch("app.utils.video_archiver.run_ffmpeg")
    @patch("app.utils.video_archiver.Image.open")
    @patch("app.utils.video_archiver._is_valid_png", return_value=True)
    @patch("app.utils.video_archiver.is_mostly_blank", return_value=False)
    @patch("glob.glob")
    def test_compile_to_video_skips_missing_files(
        self, mock_glob, mock_blank, mock_is_valid, mock_open, mock_run_ffmpeg
    ):
        camera_name = os.path.basename(self.temp_dir)
        mock_glob.return_value = [
            f"{camera_name}_20260422145530.png",
            f"{camera_name}_20260422150205.png",
            f"{camera_name}_20260422152847.png",
            f"{camera_name}_20260422153026.png",
        ]

        mock_glob.return_value = [
            os.path.join(self.temp_dir, frame) for frame in mock_glob.return_value
        ]
        for frame in mock_glob.return_value[1:]:
            with open(frame, "wb") as handle:
                handle.write(b"fixture")

        def size_side_effect(path):
            if "145530" in path:
                raise FileNotFoundError
            return 2048

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=False),
            patch("os.path.getmtime", return_value=1724516114),
            patch("os.path.getctime", return_value=1724516115),
            patch("os.path.getsize", side_effect=size_side_effect),
            patch("os.rename"),
            patch("app.utils.video_archiver.get_templates", return_value={}),
        ):
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_open.return_value.__exit__.return_value = None
            mock_run_ffmpeg.return_value.returncode = 0
            compile_to_video(self.temp_dir, self.temp_dir)

        self.assertTrue(mock_run_ffmpeg.called)

    @patch("app.utils.video_archiver.compile_to_video")
    def test_archive_screenshots(self, mock_compile_to_video):
        with (
            patch("app.utils.video_archiver.ARCHIVE_BATCH_SIZE", 0),
            patch("app.utils.video_archiver.FileLock", return_value=nullcontext()),
            patch("os.listdir", return_value=["camera1", "camera2"]),
            patch("os.path.isdir", return_value=True),
        ):
            archive_screenshots()
        self.assertEqual(mock_compile_to_video.call_count, 2)

    @patch("app.utils.video_archiver.logging.exception")
    @patch("app.utils.video_archiver.compile_to_video", side_effect=Exception("fail"))
    def test_archive_screenshots_logs_error(self, mock_compile_to_video, mock_log):
        with (
            patch("app.utils.video_archiver.ARCHIVE_BATCH_SIZE", 0),
            patch("app.utils.video_archiver.FileLock", return_value=nullcontext()),
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

    def test_ffmpeg_hwaccel_helpers_detect_and_strip_cuda_failure(self):
        command = ["ffmpeg", "-hwaccel", "cuda", "-i", "input.mp4", "out.mp4"]
        self.assertEqual(
            _ffmpeg_command_without_hwaccel(command),
            ["ffmpeg", "-i", "input.mp4", "out.mp4"],
        )
        self.assertTrue(
            _ffmpeg_error_suggests_hwaccel_failure(
                "Device setup failed for decoder on input stream"
            )
        )
        self.assertFalse(_ffmpeg_error_suggests_hwaccel_failure("Invalid data found"))

    @patch("subprocess.run")
    def test_run_ffmpeg_retries_without_hwaccel_on_cuda_failure(self, mock_run):
        failed = MagicMock(
            returncode=1,
            stdout="",
            stderr="No device available for decoder: device type cuda needed",
        )
        recovered = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = [failed, recovered]

        with patch("app.utils.video_archiver.FFMPEG_HWACCEL", "cuda"):
            result = run_ffmpeg(
                ["ffmpeg", "-hwaccel", "cuda", "-i", "input.mp4", "out.mp4"]
            )

        self.assertIs(result, recovered)
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(
            mock_run.call_args_list[1].args[0],
            ["ffmpeg", "-i", "input.mp4", "out.mp4"],
        )

    @patch("app.utils.video_archiver._pipe_ffmpeg_frames_once")
    def test_pipe_ffmpeg_frames_retries_without_hwaccel_on_cuda_failure(
        self, mock_pipe_once
    ):
        failed = MagicMock(returncode=1)
        recovered = MagicMock(returncode=0)
        mock_pipe_once.side_effect = [
            (failed, b"", b"Failed to create CUDA device"),
            (recovered, b"", b""),
        ]

        with patch("app.utils.video_archiver.FFMPEG_HWACCEL", "cuda"):
            result = pipe_ffmpeg_frames(
                ["ffmpeg", "-hwaccel", "cuda", "-i", "pipe:0", "out.mp4"],
                ["frame1.png"],
            )

        self.assertIs(result, recovered)
        self.assertEqual(mock_pipe_once.call_count, 2)
        self.assertEqual(
            mock_pipe_once.call_args_list[1].args[0],
            ["ffmpeg", "-i", "pipe:0", "out.mp4"],
        )


if __name__ == "__main__":
    unittest.main()
