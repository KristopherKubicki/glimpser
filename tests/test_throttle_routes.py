import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestHeavyRouteThrottle(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        self.throttle_patch = patch("app.utils.throttle._last_calls", {})
        self.throttle_patch.start()
        self.time_patch = patch("app.utils.throttle.time.time", return_value=0)
        self.time_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.throttle_patch.stop()
        self.time_patch.stop()

    @patch("app.routes.video_archiver.compile_to_teaser")
    def test_compile_teaser_throttled(self, mock_compile):
        resp1 = self.client.post("/compile_teaser")
        self.assertEqual(resp1.status_code, 200)
        resp2 = self.client.post("/compile_teaser")
        self.assertEqual(resp2.status_code, 429)
        mock_compile.assert_called_once()

    @patch("app.routes._concat_copy")
    @patch("app.routes.video_archiver.create_blank_video")
    def test_clip_throttled(self, mock_blank, mock_concat):
        with tempfile.TemporaryDirectory() as tmpdir:
            camera_path = os.path.join(tmpdir, "cam1")
            os.makedirs(camera_path)
            with open(os.path.join(camera_path, "final_1.mp4"), "wb") as f:
                f.write(b"0")
            with (
                patch("app.routes.VIDEO_DIRECTORY", tmpdir),
                patch("app.routes.send_file") as mock_send,
            ):

                def fake_blank(duration, output, *, width=None, height=None):
                    with open(output, "w"):
                        pass
                    return True

                mock_blank.side_effect = fake_blank

                def fake_concat(out, parts, clip_len):
                    with open(out, "w"):
                        pass
                    return True

                mock_concat.side_effect = fake_concat

                resp1 = self.client.get("/clip/cam1")
                resp2 = self.client.get("/clip/cam1")
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 429)
        mock_send.assert_called_once()
        mock_concat.assert_called_once()
        mock_blank.assert_not_called()


if __name__ == "__main__":
    unittest.main()
