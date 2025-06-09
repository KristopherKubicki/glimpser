import os
import sys
import unittest
import tempfile
from pathlib import Path
from flask import Flask
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.routes as routes
from app.routes import init_routes
import app.config as config


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
            os.utime(f1, (1, 1))
            os.utime(f2, (2, 2))
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("app.routes.send_file") as mock_send,
            ):

                def fake_blank(duration, output, width=None, height=None):
                    with open(output, "w"):
                        pass
                    return True

                mock_blank.side_effect = fake_blank

                def fake_concat(out, parts, clip_len):
                    with open(out, "w"):
                        pass
                    return True

                mock_concat.side_effect = fake_concat
                resp = self.client.get("/clip/cam1")

        self.assertEqual(resp.status_code, 200)
        expected = Path(tmpdir, "cam1", "clip.mp4")
        mock_send.assert_called_with(expected, conditional=True)
        mock_concat.assert_called_once()
        mock_blank.assert_called_once()

    @patch("app.routes._concat_copy", return_value=False)
    @patch("app.routes.video_archiver.create_blank_video")
    def test_clip_blank_fallback(self, mock_blank, mock_concat):
        with tempfile.TemporaryDirectory() as tmpdir:
            camera_path = os.path.join(tmpdir, "cam1")
            os.makedirs(camera_path)
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("app.routes.send_file") as mock_send,
            ):

                def fake_blank(duration, output, width=None, height=None):
                    with open(output, "w"):
                        pass
                    return True

                mock_blank.side_effect = fake_blank
                resp = self.client.get("/clip/cam1")

        self.assertEqual(resp.status_code, 200)
        expected = Path(tmpdir, "cam1", "clip.mp4")
        mock_send.assert_called_with(expected, conditional=True)
        self.assertEqual(mock_blank.call_count, 2)


if __name__ == "__main__":
    unittest.main()
