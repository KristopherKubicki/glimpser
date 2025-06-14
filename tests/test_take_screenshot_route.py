import os
import shutil
import sys
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestTakeScreenshotRoute(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sshot_dir = "test_take_screenshot"
        os.makedirs(os.path.join(self.repo_root, self.sshot_dir, "cam1"), exist_ok=True)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.tpl_patch = patch("app.routes.template_manager.get_templates")
        self.update_patch = patch("app.routes.scheduling.update_camera")
        self.login_patch.start()
        self.sc_patch.start()
        self.mock_templates = self.tpl_patch.start()
        self.mock_update = self.update_patch.start()
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        self.tpl_patch.stop()
        self.update_patch.stop()
        shutil.rmtree(os.path.join(self.repo_root, self.sshot_dir), ignore_errors=True)

    def test_motion_query_passed(self):
        self.mock_templates.return_value = {"cam1": {"name": "cam1"}}
        resp = self.client.get("/take_screenshot/cam1?motion=true")
        self.assertEqual(resp.status_code, 200)
        self.mock_update.assert_called_with("cam1", {"name": "cam1"}, motion=True)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
