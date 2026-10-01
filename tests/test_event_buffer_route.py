import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from flask import Flask
from PIL import Image

from app.blueprints.assets import embedded_event_buffer_token
from app.routes import init_routes


class TestEventBufferRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda view: view)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.template_manager.get_template")
    def test_event_buffer_test_accepts_lan_camera(self, mock_get_template):
        mock_get_template.return_value = {"url": "http://192.168.1.30/snapshot.jpg"}

        response = self.client.post(
            "/templates/FrontDoor/event_buffer/test",
            data={
                "url": "http://192.168.1.30/snapshot.jpg",
                "event_buffer_enabled": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertIn("backoff", payload["message"])

    @patch("app.routes.template_manager.get_template")
    def test_event_buffer_test_blocks_browser_capture(self, mock_get_template):
        mock_get_template.return_value = {"url": "http://192.168.1.30/snapshot.jpg"}

        response = self.client.post(
            "/templates/FrontDoor/event_buffer/test",
            data={
                "url": "http://192.168.1.30/snapshot.jpg",
                "browser": "on",
                "event_buffer_enabled": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("browser captures", payload["message"])

    @patch("app.routes.event_buffer.build_event_gif")
    def test_event_buffer_gif_serves_media(self, mock_build):
        with NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            Image.new("RGB", (8, 8), (0, 128, 255)).save(path, "GIF")
            mock_build.return_value = path

            response = self.client.get("/event_buffer/FrontDoor.gif?wait=0")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/gif")
            mock_build.assert_called_once_with("FrontDoor", wait_post=0.0)
        finally:
            path.unlink(missing_ok=True)

    @patch("app.routes.event_buffer.build_event_gif")
    def test_embedded_event_buffer_gif_requires_token(self, mock_build):
        with NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            Image.new("RGB", (8, 8), (255, 128, 0)).save(path, "GIF")
            mock_build.return_value = path
            token = embedded_event_buffer_token("FrontDoor", "secret")

            with patch("app.routes.API_KEY", "secret"):
                denied = self.client.get("/embedded_event_buffer/FrontDoor.gif?wait=0")
                allowed = self.client.get(
                    f"/embedded_event_buffer/FrontDoor.gif?wait=0&token={token}"
                )

            self.assertEqual(denied.status_code, 401)
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(allowed.mimetype, "image/gif")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
