import os
import io
import shutil
import unittest
from flask import Flask
from PIL import Image
from unittest.mock import patch

from app.routes import init_routes


class TestUploadNavIcon(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.static_dir = os.path.join(self.repo_root, "test_static")
        os.makedirs(os.path.join(self.static_dir, "img"), exist_ok=True)
        self.app = Flask(__name__, static_folder=self.static_dir)
        self.app.config["SECRET_KEY"] = "test"
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.update_patch = patch("app.routes.update_setting")
        self.login_patch.start()
        self.mock_update = self.update_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.update_patch.stop()
        shutil.rmtree(self.static_dir, ignore_errors=True)

    def test_upload_nav_icon(self):
        img_bytes = io.BytesIO()
        Image.new("RGB", (150, 22)).save(img_bytes, format="PNG")
        img_bytes.seek(0)
        data = {"logo_file": (img_bytes, "logo.png")}
        resp = self.client.post(
            "/upload_nav_icon", data=data, content_type="multipart/form-data"
        )
        self.assertEqual(resp.status_code, 302)
        saved = os.path.join(self.static_dir, "img", "logo.png")
        self.assertTrue(os.path.exists(saved))
        self.mock_update.assert_called_with("NAV_ICON", "img/logo.png")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
