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
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch("app.utils.screenshots.subprocess.run") as mock_run,
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

    def test_hdhomerun_profile_uses_other_probe_and_no_keyframe_skip(self):
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
                    "app.utils.screenshots.shutil.which", return_value="/usr/bin/ffmpeg"
                ),
                patch("app.utils.screenshots.subprocess.run") as mock_run,
                patch("app.utils.screenshots.os.makedirs"),
                patch("app.utils.screenshots.os.path.exists", return_value=True),
                patch("app.utils.screenshots.os.listdir", return_value=["f.png"]),
                patch("app.utils.screenshots.os.path.getsize", return_value=1),
                patch("app.utils.screenshots.shutil.move"),
                patch("app.utils.screenshots._is_valid_png", return_value=True),
                patch("app.utils.screenshots.add_timestamp"),
            ):
                ss.capture_frame_from_stream(
                    "http://192.168.2.193:5004/auto/v2.1",
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


if __name__ == "__main__":
    unittest.main()
