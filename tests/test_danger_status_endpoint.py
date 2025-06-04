import os
import sys
import unittest
from flask import Flask
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestDangerStatusEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.is_chrome_debug_port_open", return_value=True)
    @patch("app.routes.check_user_activity", return_value=False)
    def test_danger_ready(self, mock_idle, mock_port):
        resp = self.client.get("/danger_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "port_open": True,
                "idle": True,
                "enabled": True,
                "ready": True,
            },
        )

    @patch("app.routes.is_chrome_debug_port_open", return_value=False)
    @patch("app.routes.check_user_activity", return_value=False)
    def test_danger_port_closed(self, mock_idle, mock_port):
        """Should report not ready when the debug port is closed."""
        resp = self.client.get("/danger_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "port_open": False,
                "idle": True,
                "enabled": True,
                "ready": False,
            },
        )

    @patch("app.routes.is_chrome_debug_port_open", return_value=True)
    @patch("app.routes.check_user_activity", return_value=True)
    def test_danger_user_active(self, mock_idle, mock_port):
        """Should report not ready when user activity is detected."""
        resp = self.client.get("/danger_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "port_open": True,
                "idle": False,
                "enabled": True,
                "ready": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
