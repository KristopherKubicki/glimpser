import os
import shutil
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestStreamPngRoute(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sshot_dir = "test_stream_png"
        os.makedirs(os.path.join(self.repo_root, self.sshot_dir, "cam1"), exist_ok=True)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.tpl_patch = patch("app.routes.template_manager.get_templates")
        self.login_patch.start()
        self.sc_patch.start()
        self.mock_tpl = self.tpl_patch.start()
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        self.tpl_patch.stop()
        shutil.rmtree(os.path.join(self.repo_root, self.sshot_dir), ignore_errors=True)

    def test_empty_directory_returns_404(self):
        self.mock_tpl.return_value = {"cam1": {"name": "cam1"}}
        resp = self.client.get("/stream.png")
        self.assertEqual(resp.status_code, 404)

    def test_returns_latest_image(self):
        self.mock_tpl.return_value = {"cam1": {"name": "cam1"}}
        img_path = os.path.join(self.repo_root, self.sshot_dir, "cam1", "cam1_1.png")
        Image.new("RGB", (1, 1)).save(img_path)
        resp = self.client.get("/stream.png")
        self.assertEqual(resp.status_code, 200)

    def test_ignores_missing_files(self):
        self.mock_tpl.return_value = {"cam1": {"name": "cam1"}}
        img_dir = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        valid = os.path.join(img_dir, "cam1_valid.png")
        missing = os.path.join(img_dir, "cam1_missing.png")
        Image.new("RGB", (1, 1)).save(valid)

        def fake_glob(_):
            return [missing, valid]

        orig_getmtime = os.path.getmtime

        def fake_getmtime(path):
            if path == missing:
                raise FileNotFoundError
            return orig_getmtime(path)

        with (
            patch("glob.glob", side_effect=fake_glob),
            patch("os.path.getmtime", side_effect=fake_getmtime),
        ):
            resp = self.client.get("/stream.png")
        self.assertEqual(resp.status_code, 200)

    def test_camera_parameter(self):
        self.mock_tpl.return_value = {
            "cam1": {"name": "cam1", "groups": "g1"},
            "cam2": {"name": "cam2", "groups": "g2"},
        }
        img_dir1 = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        img1 = os.path.join(img_dir1, "shot.png")
        Image.new("RGB", (1, 1)).save(img1)
        os.symlink(img1, os.path.join(img_dir1, "latest_camera.png"))

        img_dir2 = os.path.join(self.repo_root, self.sshot_dir, "cam2")
        os.makedirs(img_dir2, exist_ok=True)
        img2 = os.path.join(img_dir2, "shot.png")
        Image.new("RGB", (1, 1)).save(img2)
        os.symlink(img2, os.path.join(img_dir2, "latest_camera.png"))

        resp = self.client.get("/stream.png?camera=cam1")
        with open(img1, "rb") as f:
            self.assertEqual(resp.data, f.read())

    def test_group_parameter(self):
        self.mock_tpl.return_value = {"cam1": {"name": "cam1", "groups": "g1"}}
        img_dir1 = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        img1 = os.path.join(img_dir1, "shot.png")
        Image.new("RGB", (1, 1)).save(img1)
        os.symlink(img1, os.path.join(img_dir1, "latest_camera.png"))
        group_link = os.path.join(self.repo_root, self.sshot_dir, "g1_latest_camera.png")
        os.symlink(img1, group_link)

        resp = self.client.get("/stream.png?group=g1")
        with open(img1, "rb") as f:
            self.assertEqual(resp.data, f.read())

    def test_skips_invalid_png(self):
        self.mock_tpl.return_value = {"cam1": {"name": "cam1"}}
        img_dir = os.path.join(self.repo_root, self.sshot_dir, "cam1")
        invalid = os.path.join(img_dir, "cam1_bad.png")
        with open(invalid, "wb") as fh:
            fh.write(b"not an image")
        valid = os.path.join(img_dir, "cam1_good.png")
        Image.new("RGB", (1, 1)).save(valid)
        resp = self.client.get("/stream.png")
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.data), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
