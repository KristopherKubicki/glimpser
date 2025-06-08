import os
import sys
import unittest
import tempfile
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
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.video_archiver.compile_videos")
    @patch("app.routes.video_archiver.get_video_duration", return_value=60)
    @patch("glob.glob", return_value=["v1.mp4", "v2.mp4"])
    @patch("os.path.getmtime", side_effect=[2, 1])
    @patch("os.path.exists", return_value=True)
    @patch("app.routes.send_file")
    def test_clip_default(
        self,
        mock_send,
        mock_exists,
        mock_getmtime,
        mock_glob,
        mock_duration,
        mock_compile,
    ):
        resp = self.client.get("/clip/cam1")
        self.assertEqual(resp.status_code, 200)
        expected = os.path.join(
            os.path.dirname(routes.__file__),
            "..",
            config.VIDEO_DIRECTORY,
            "cam1",
            "clip.mp4",
        )
        mock_compile.assert_called_once()
        mock_send.assert_called_with(expected)

    @patch("app.routes.video_archiver.create_blank_video")
    @patch("app.routes.video_archiver.compile_videos", return_value=None)
    @patch("app.routes.video_archiver.get_video_duration", return_value=60)
    def test_clip_blank_fallback(
        self,
        mock_duration,
        mock_compile,
        mock_blank,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            camera_path = os.path.join(tmpdir, "cam1")
            os.makedirs(camera_path)
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("glob.glob", return_value=[]),
                patch("os.path.getmtime", return_value=1),
                patch("app.routes.send_file") as mock_send,
            ):

                def fake_blank(duration, output):
                    with open(output, "w"):
                        pass
                    return True

                mock_blank.side_effect = fake_blank
                resp = self.client.get("/clip/cam1")

        self.assertEqual(resp.status_code, 200)
        expected = os.path.join(tmpdir, "cam1", "clip.mp4")
        mock_send.assert_called_with(expected)
        mock_blank.assert_called_once()


if __name__ == "__main__":
    unittest.main()
