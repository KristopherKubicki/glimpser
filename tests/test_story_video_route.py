import unittest
from unittest.mock import ANY, patch

from flask import Flask

from app.routes import init_routes


class TestStoryVideoRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.compile_patch = patch("app.routes.video_archiver.compile_caption_story")
        self.throttle_patch = patch("app.utils.throttle._last_calls", {})
        self.login_patch.start()
        self.mock_compile = self.compile_patch.start()
        self.throttle_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.compile_patch.stop()
        self.throttle_patch.stop()

    def test_story_video_success(self):
        self.mock_compile.return_value = True
        with patch("app.routes.send_file") as mock_send:
            resp = self.client.post(
                "/story_video",
                json={"images": ["a.png"], "captions": ["hi"]},
            )
        self.assertEqual(resp.status_code, 200)
        self.mock_compile.assert_called_once()
        mock_send.assert_called_once()

    def test_story_video_frames_payload(self):
        self.mock_compile.return_value = True
        with patch("app.routes.send_file") as mock_send:
            resp = self.client.post(
                "/story_video",
                json={"frames": [{"image": "one.png", "caption": "hi", "duration": 2}]},
            )
        self.assertEqual(resp.status_code, 200)
        self.mock_compile.assert_called_once_with(
            ["one.png"], ["hi"], ANY, durations=[2]
        )
        mock_send.assert_called_once()

    def test_story_video_bad_request(self):
        resp = self.client.post("/story_video", json={"images": ["a.png"]})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
