import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class TestCaptureStreamConfig(unittest.TestCase):
    def _reload_modules(self, env):
        patcher = patch.dict(os.environ, env)
        patcher.start()
        import app.utils.screenshots as ss
        from app import config

        importlib.reload(config)
        importlib.reload(ss)
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: importlib.reload(config))
        self.addCleanup(lambda: importlib.reload(ss))
        return ss

    def test_custom_analyze_and_probe_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            ss = self._reload_modules(
                {
                    "GLIMPSER_DATABASE_PATH": db_path,
                    "GLIMPSER_BACKUP_PATH": os.path.join(tmp, "b.json"),
                    "ANALYZE_DURATION_DEFAULT": "3M",
                    "PROBE_SIZE_DEFAULT": "2M",
                }
            )

            with (
                patch(
                    "app.utils.screenshots._probe_stream_with_ffprobe",
                    return_value=True,
                ),
                patch(
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch("app.utils.screenshots.run_capture_command") as mock_run,
                patch("app.utils.screenshots.os.makedirs"),
                patch("app.utils.screenshots.os.path.exists", return_value=True),
                patch("app.utils.screenshots.os.listdir", return_value=["f.png"]),
                patch("app.utils.screenshots.os.path.getsize", return_value=1),
                patch("app.utils.screenshots.shutil.move"),
                patch("app.utils.screenshots._is_valid_png", return_value=True),
                patch("app.utils.screenshots.add_timestamp"),
            ):
                ss.capture_frame_from_stream("http://example.com", "out.png")

            cmd = mock_run.call_args.args[0]
            a_idx = cmd.index("-analyzeduration")
            p_idx = cmd.index("-probesize")
            self.assertEqual(cmd[a_idx + 1], "3M")
            self.assertEqual(cmd[p_idx + 1], "2M")
            self.assertEqual(cmd[-3:-1], ["-compression_level", "1"])
            self.assertTrue(cmd[-1].endswith(".png"))

    def test_slow_rtsp_keeps_warmup_and_uses_lossless_fast_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            ss = self._reload_modules(
                {
                    "GLIMPSER_DATABASE_PATH": db_path,
                    "GLIMPSER_BACKUP_PATH": os.path.join(tmp, "b.json"),
                    "ANALYZE_DURATION_DEFAULT": "3M",
                    "PROBE_SIZE_DEFAULT": "2M",
                }
            )

            with (
                patch(
                    "app.utils.screenshots._probe_stream_with_ffprobe",
                    return_value=True,
                ),
                patch(
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch.dict(
                    ss.capture_policy.CAPTURE_POLICY,
                    {"slow_rtsp_cameras": ["test-slow"]},
                ),
                patch("app.utils.screenshots.run_capture_command") as mock_run,
                patch("app.utils.screenshots.os.makedirs"),
                patch("app.utils.screenshots.os.path.exists", return_value=True),
                patch("app.utils.screenshots.os.listdir", return_value=["f.png"]),
                patch("app.utils.screenshots.os.path.getsize", return_value=1),
                patch("app.utils.screenshots.shutil.move"),
                patch("app.utils.screenshots._is_valid_png", return_value=True),
                patch("app.utils.screenshots.add_timestamp"),
            ):
                ss.capture_frame_from_stream(
                    "rtsp://example.com/live", "out.png", name="test-slow"
                )

            cmd = mock_run.call_args.args[0]
            self.assertEqual(cmd[cmd.index("-ss") + 1], "12")
            self.assertEqual(cmd[cmd.index("-frames:v") + 1], "3")
            self.assertEqual(cmd[-3:-1], ["-compression_level", "1"])
            self.assertTrue(cmd[-1].endswith(".png"))

    def test_hdhomerun_profile_uses_other_probe_and_minimal_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            ss = self._reload_modules(
                {
                    "GLIMPSER_DATABASE_PATH": db_path,
                    "GLIMPSER_BACKUP_PATH": os.path.join(tmp, "b.json"),
                    "ANALYZE_DURATION_DEFAULT": "3M",
                    "PROBE_SIZE_DEFAULT": "2M",
                    "ANALYZE_DURATION_OTHER": "9M",
                    "PROBE_SIZE_OTHER": "8M",
                    "NUM_FRAMES": "5",
                }
            )

            with (
                patch(
                    "app.utils.screenshots._probe_stream_with_ffprobe",
                    return_value=True,
                ),
                patch(
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch("app.utils.screenshots.run_capture_command") as mock_run,
                patch("app.utils.screenshots.os.makedirs"),
                patch("app.utils.screenshots.os.path.exists", return_value=True),
                patch("app.utils.screenshots.os.listdir", return_value=["f.png"]),
                patch("app.utils.screenshots.os.path.getsize", return_value=1),
                patch("app.utils.screenshots.shutil.move"),
                patch("app.utils.screenshots._is_valid_png", return_value=True),
                patch("app.utils.screenshots.add_timestamp"),
            ):
                ss.capture_frame_from_stream(
                    "http://192.0.2.193:5004/auto/v2.1",
                    "out.png",
                )

            cmd = mock_run.call_args.args[0]
            a_idx = cmd.index("-analyzeduration")
            p_idx = cmd.index("-probesize")
            frames_idx = cmd.index("-frames:v")
            self.assertEqual(cmd[a_idx + 1], "9M")
            self.assertEqual(cmd[p_idx + 1], "8M")
            self.assertEqual(cmd[frames_idx + 1], "2")
            self.assertNotIn("-skip_frame", cmd)
            self.assertNotIn("-headers", cmd)
            self.assertNotIn("-hwaccel", cmd)
            self.assertNotIn("-movflags", cmd)

    def test_hdhomerun_stream_skips_preflight_probes_and_uses_longer_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            ss = self._reload_modules(
                {
                    "GLIMPSER_DATABASE_PATH": db_path,
                    "GLIMPSER_BACKUP_PATH": os.path.join(tmp, "b.json"),
                }
            )

            with (
                patch(
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch("app.utils.screenshots._probe_stream_with_ffprobe") as mock_probe,
                patch("app.utils.screenshots._ffmpeg_null_probe") as mock_null_probe,
                patch("app.utils.screenshots.run_capture_command") as mock_run,
                patch("app.utils.screenshots.os.makedirs"),
                patch("app.utils.screenshots.os.path.exists", return_value=True),
                patch("app.utils.screenshots.os.listdir", return_value=["f.png"]),
                patch("app.utils.screenshots.os.path.getsize", return_value=1),
                patch("app.utils.screenshots.shutil.move"),
                patch("app.utils.screenshots._is_valid_png", return_value=True),
                patch("app.utils.screenshots.add_timestamp"),
            ):
                ss.capture_frame_from_stream(
                    "http://192.0.2.194:5004/auto/v32.1",
                    "out.png",
                    timeout=10,
                )

            mock_probe.assert_not_called()
            mock_null_probe.assert_not_called()
            self.assertEqual(mock_run.call_args.kwargs["timeout"], 20)

    def test_hdhomerun_stream_honors_longer_template_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            ss = self._reload_modules(
                {
                    "GLIMPSER_DATABASE_PATH": db_path,
                    "GLIMPSER_BACKUP_PATH": os.path.join(tmp, "b.json"),
                }
            )

            with (
                patch(
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch("app.utils.screenshots._probe_stream_with_ffprobe") as mock_probe,
                patch("app.utils.screenshots._ffmpeg_null_probe") as mock_null_probe,
                patch("app.utils.screenshots.run_capture_command") as mock_run,
                patch("app.utils.screenshots.os.makedirs"),
                patch("app.utils.screenshots.os.path.exists", return_value=True),
                patch("app.utils.screenshots.os.listdir", return_value=["f.png"]),
                patch("app.utils.screenshots.os.path.getsize", return_value=1),
                patch("app.utils.screenshots.shutil.move"),
                patch("app.utils.screenshots._is_valid_png", return_value=True),
                patch("app.utils.screenshots.add_timestamp"),
            ):
                ss.capture_frame_from_stream(
                    "http://192.0.2.194:5004/auto/v32.1",
                    "out.png",
                    timeout=45,
                )

            mock_probe.assert_not_called()
            mock_null_probe.assert_not_called()
            self.assertEqual(mock_run.call_args.kwargs["timeout"], 45)


if __name__ == "__main__":
    unittest.main()
