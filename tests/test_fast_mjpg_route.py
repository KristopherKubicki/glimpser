import os
import shutil
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from PIL import Image

from app.routes import init_routes


class TestFastMjpgRoute(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sshot_dir = "test_fast_mjpg"
        os.makedirs(os.path.join(self.repo_root, self.sshot_dir, "cam1"), exist_ok=True)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.tpl_patch = patch("app.routes.template_manager.get_template")
        self.update_patch = patch("app.routes.scheduling.update_camera")
        self.login_patch.start()
        self.sc_patch.start()
        self.mock_tpl = self.tpl_patch.start()
        self.mock_update = self.update_patch.start()

        def create_frame(name, template):
            img_path = os.path.join(
                self.repo_root, self.sshot_dir, name, "latest_camera.png"
            )
            Image.new("RGB", (1, 1)).save(img_path)

        self.mock_update.side_effect = create_frame
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        self.tpl_patch.stop()
        self.update_patch.stop()
        shutil.rmtree(os.path.join(self.repo_root, self.sshot_dir), ignore_errors=True)

    def test_route_returns_200(self):
        self.mock_tpl.return_value = {"name": "cam1", "url": "http://example.com"}
        resp = self.client.get("/fast_stream.mjpg?camera=cam1")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
