import os
import sys
import unittest
from flask import Flask
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.routes as routes
from app.routes import init_routes
import app.config as config


class TestRecentClipRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.clip_patch = patch("app.routes.video_archiver.assemble_recent_clip")
        self.send_patch = patch("app.routes.send_file")
        self.exists_patch = patch("os.path.exists", return_value=True)
        self.login_patch.start()
        self.mock_clip = self.clip_patch.start()
        self.mock_send = self.send_patch.start()
        self.exists_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.clip_patch.stop()
        self.send_patch.stop()
        self.exists_patch.stop()

    def test_recent_clip_success(self):
        self.mock_clip.return_value = "/tmp/clip.mp4"
        resp = self.client.get("/recent_clip/cam1")
        self.assertEqual(resp.status_code, 200)
        self.mock_clip.assert_called_with("cam1", config.RECENT_CLIP_DURATION)
        self.mock_send.assert_called_with("/tmp/clip.mp4")

    def test_recent_clip_missing(self):
        self.mock_clip.return_value = None
        resp = self.client.get("/recent_clip/cam1")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
