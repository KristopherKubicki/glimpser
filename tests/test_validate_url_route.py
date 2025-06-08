import unittest
from flask import Flask
from unittest.mock import patch

from app.routes import init_routes


class TestValidateUrlRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.camera_fix.check_camera_template")
    def test_validate_url_success(self, mock_check):
        mock_check.return_value = {"valid_url": True, "url_error": ""}
        resp = self.client.get("/validate_url?url=http://x")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"valid": True, "error": ""})

    def test_validate_url_invalid(self):
        resp = self.client.get("/validate_url?url=ftp://x")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"valid": False, "error": "invalid"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
