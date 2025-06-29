"""Tests for camera diagnostics route."""
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestCameraDiagnosticsRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.socket.gethostbyname", return_value="1.2.3.4")
    @patch("app.routes.camera_discovery._classify_device", return_value="camera")
    @patch(
        "app.routes.camera_discovery._fetch_http_banner",
        return_value={"server": "CamOS"},
    )
    @patch("app.routes.camera_discovery._detect_open_ports", return_value=[80])
    @patch("app.routes.camera_discovery._ping_latency", return_value=5.0)
    @patch("app.routes.template_manager.get_template")
    def test_diagnostics_success(
        self,
        mock_get_template,
        mock_ping,
        mock_ports,
        mock_banner,
        mock_classify,
        mock_gethost,
    ):
        mock_get_template.return_value = {"url": "http://cam"}
        resp = self.client.get("/camera_diagnostics/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "ip": "1.2.3.4",
                "ping_ms": 5.0,
                "open_ports": [80],
                "server": "CamOS",
                "device_type": "camera",
            },
        )

    @patch("app.routes.template_manager.get_template", return_value=None)
    def test_diagnostics_not_found(self, mock_get):
        resp = self.client.get("/camera_diagnostics/missing")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
