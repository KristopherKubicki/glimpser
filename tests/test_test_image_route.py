import os
import sys
import shutil
import unittest
from flask import Flask
from PIL import Image
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestTestImageRoute(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sshot_dir = "test_test_image"
        os.makedirs(os.path.join(self.repo_root, self.sshot_dir, "cam1"), exist_ok=True)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.login_patch.start()
        self.sc_patch.start()
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        shutil.rmtree(os.path.join(self.repo_root, self.sshot_dir), ignore_errors=True)

    def test_global_test_image(self):
        img_path = os.path.join(self.repo_root, self.sshot_dir, "test_image.png")
        Image.new("RGB", (1, 1)).save(img_path)
        resp = self.client.get("/test_image")
        self.assertEqual(resp.status_code, 200)

    def test_camera_parameter(self):
        img_dir = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        img_path = os.path.join(img_dir, "test_image.png")
        Image.new("RGB", (1, 1)).save(img_path)
        resp = self.client.get("/test_image?camera=cam1")
        self.assertEqual(resp.status_code, 200)

    def test_time_parameter(self):
        img_dir = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        ts = "20230101010101"
        img_name = f"{ts}_motion.png"
        img_path = os.path.join(img_dir, img_name)
        Image.new("RGB", (1, 1)).save(img_path)
        resp = self.client.get(f"/test_image?camera=cam1&time={ts}")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
