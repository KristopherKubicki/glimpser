import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestListingEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        # Bypass authentication for route registration
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.template_manager.get_videos_for_template")
    def test_list_videos(self, mock_get_videos):
        mock_get_videos.return_value = ["file1.mp4"]
        resp = self.client.get("/videos/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"videos": ["file1.mp4"]})

    @patch("app.routes.template_manager.get_screenshots_for_template")
    def test_list_screenshots(self, mock_get_shots):
        mock_get_shots.return_value = ["shot1.png"]
        resp = self.client.get("/screenshots/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"screenshots": ["shot1.png"]})


if __name__ == "__main__":
    unittest.main()
