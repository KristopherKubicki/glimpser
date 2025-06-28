import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import app.config as config
import app.routes as routes
from app.routes import init_routes


class TestClipRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.throttle_patch = patch("app.utils.throttle._last_calls", {})
        self.login_patch.start()
        self.throttle_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.throttle_patch.stop()

    @patch("app.routes.video_archiver.create_blank_video")
    @patch("app.routes._concat_copy")
    def test_clip_default(self, mock_concat, mock_blank):
        with tempfile.TemporaryDirectory() as tmpdir:
            camera_path = os.path.join(tmpdir, "cam1")
            os.makedirs(camera_path)
            f1 = os.path.join(camera_path, "final_1.mp4")
            f2 = os.path.join(camera_path, "final_2.mp4")
            open(f1, "w").close()
            open(f2, "w").close()
            in_proc = os.path.join(camera_path, "in_process.mp4")
            open(in_proc, "w").close()
            os.utime(f1, (1, 1))
            os.utime(f2, (2, 2))
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("app.routes.CLIPS_DIRECTORY", tmpdir),
                patch("app.routes.send_file") as mock_send,
            ):

                def fake_concat(out, parts, clip_len):
                    with open(out, "w"):
                        pass
                    return True

                mock_concat.side_effect = fake_concat
                resp = self.client.get("/clip/cam1")

        self.assertEqual(resp.status_code, 200)
        expected = Path(tmpdir, "cam1.mp4")
        mock_send.assert_called_with(expected, conditional=True)
        mock_concat.assert_called_once()
        mock_blank.assert_not_called()

    @patch("app.routes._concat_copy", return_value=False)
    @patch("app.routes.video_archiver.create_blank_video")
    def test_clip_blank_fallback(self, mock_blank, mock_concat):
        with tempfile.TemporaryDirectory() as tmpdir:
            camera_path = os.path.join(tmpdir, "cam1")
            os.makedirs(camera_path)
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("app.routes.CLIPS_DIRECTORY", tmpdir),
                patch("app.routes.send_file") as mock_send,
            ):

                def fake_blank(duration, output, width=None, height=None):
                    with open(output, "w"):
                        pass
                    return True

                mock_blank.side_effect = fake_blank
                resp = self.client.get("/clip/cam1")

        self.assertEqual(resp.status_code, 200)
        expected = Path(tmpdir, "cam1.mp4")
        mock_send.assert_called_with(expected, conditional=True)
        mock_blank.assert_called_once()

    @patch("app.routes.scheduling.get_system_metrics")
    def test_clip_busy_returns_last_video(self, mock_metrics):
        mock_metrics.return_value = {
            "cpu_usage": config.WATCHDOG_CPU_THRESHOLD + 5,
            "memory_usage": 10,
            "thread_count": 200,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            camera_path = os.path.join(tmpdir, "cam1")
            os.makedirs(camera_path)
            final = os.path.join(camera_path, "final_1.mp4")
            open(final, "w").close()
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("app.routes.CLIPS_DIRECTORY", tmpdir),
                patch("app.routes.send_file") as mock_send,
            ):
                resp = self.client.get("/clip/cam1")

        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_with(final)


if __name__ == "__main__":
    unittest.main()
