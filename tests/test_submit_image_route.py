import os
import sys
import shutil
import unittest
import io
from flask import Flask
from PIL import Image
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestSubmitImageRoute(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sshot_dir = "test_submit_image"
        os.makedirs(os.path.join(self.repo_root, self.sshot_dir, "cam1"), exist_ok=True)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.tpl_patch = patch("app.routes.template_manager.get_template")
        self.update_patch = patch(
            "app.routes.template_manager.update_last_screenshot_time"
        )
        self.ts_patch = patch("app.routes.screenshots.add_timestamp")
        self.login_patch.start()
        self.sc_patch.start()
        self.mock_tpl = self.tpl_patch.start()
        self.update_patch.start()
        self.ts_patch.start()
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        self.tpl_patch.stop()
        self.update_patch.stop()
        self.ts_patch.stop()
        shutil.rmtree(os.path.join(self.repo_root, self.sshot_dir), ignore_errors=True)

    def test_submit_image_saves_file(self):
        self.mock_tpl.return_value = {"name": "cam1"}
        img_bytes = io.BytesIO()
        Image.new("RGB", (1, 1)).save(img_bytes, format="PNG")
        img_bytes.seek(0)
        data = {"file": (img_bytes, "shot.png")}
        resp = self.client.post(
            "/submit_image/cam1",
            data=data,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        files = os.listdir(os.path.join(self.repo_root, self.sshot_dir, "cam1"))
        self.assertTrue(any(f.endswith(".png") for f in files))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
