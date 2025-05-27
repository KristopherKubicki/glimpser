import os
import sys
import shutil
import unittest
from flask import Flask
from PIL import Image
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestServeScreenshot(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sshot_dir = "test_screenshots"
        self.full_base = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        os.makedirs(self.full_base, exist_ok=True)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch.start()
        self.login_patch.start()
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        shutil.rmtree(os.path.join(self.repo_root, self.sshot_dir), ignore_errors=True)

    def test_empty_screenshot_returns_404(self):
        path = os.path.join(self.full_base, "cam1_20200101.png")
        open(path, "wb").close()
        resp = self.client.get("/last_screenshot/cam1")
        self.assertEqual(resp.status_code, 404)

    def test_valid_screenshot_served(self):
        path = os.path.join(self.full_base, "cam1_20200102.png")
        Image.new("RGB", (1, 1)).save(path)
        resp = self.client.get("/last_screenshot/cam1")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
