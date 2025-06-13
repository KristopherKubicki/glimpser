import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestSuggestFixRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.template_manager.get_template")
    @patch("app.routes.camera_fix.check_camera_template")
    def test_suggest_fix_success(self, mock_check, mock_get):
        mock_get.return_value = {
            "url": "http://x",
            "popup_xpath": "",
            "dedicated_xpath": "",
        }
        mock_check.return_value = {"valid_url": False, "suggestions": ["a"]}
        resp = self.client.post("/suggest_fix/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"valid_url": False, "suggestions": ["a"]})

    @patch("app.routes.template_manager.get_template", return_value={})
    def test_suggest_fix_not_found(self, mock_get):
        resp = self.client.post("/suggest_fix/missing")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
