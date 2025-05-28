# tests/test_routes.py

import unittest
import os
import sys
from unittest.mock import patch
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes
from types import SimpleNamespace


class TestRoutes(unittest.TestCase):
    def setUp(self):
        template_dir = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "../app/templates"
        )
        self.app = Flask(__name__, template_folder=template_dir)
        self.app.config["SECRET_KEY"] = "my_secret_key"
        init_routes(self.app)
        self.client = self.app.test_client()

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 302)

    @patch("app.routes.check_password_hash")
    @patch("app.routes.SessionLocal")
    @patch("app.routes.login_attempts", {})
    def test_login_success(self, mock_session_local, mock_check_password):
        mock_check_password.return_value = True
        dummy_user = SimpleNamespace(id=1, username="testuser", password_hash="hash")

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.post(
            "/login",
            data={"username": "testuser", "password": "testpassword"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/", response.headers["Location"])

    @patch("app.routes.check_password_hash")
    @patch("app.routes.SessionLocal")
    @patch("app.routes.login_attempts", {})
    @patch("app.routes.render_template")
    def test_login_failure(
        self, mock_render_template, mock_session_local, mock_check_password
    ):
        mock_check_password.return_value = False
        dummy_user = SimpleNamespace(id=1, username="testuser", password_hash="hash")

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.post(
            "/login", data={"username": "testuser", "password": "wrongpassword"}
        )
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with("login.html")

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    def test_logout(self, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.render_template")
    def test_index(self, mock_render_template, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with("index.html")

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.get_templates")
    @patch("app.routes.render_template")
    def test_captions(
        self, mock_render_template, mock_get_templates, mock_session_local
    ):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        mock_get_templates.return_value = {"template1": {}, "template2": {}}
        response = self.client.get("/captions")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "captions.html",
            template_details=mock_get_templates.return_value,
            lcaptions=[],
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.get_templates")
    def test_get_templates(self, mock_get_templates, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        mock_get_templates.return_value = {"template1": {}, "template2": {}}
        response = self.client.get("/templates?group=all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"template1": {}, "template2": {}})

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.save_template")
    def test_save_template(self, mock_save_template, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        mock_save_template.return_value = True
        response = self.client.post(
            "/templates", json={"name": "new_template", "url": "http://example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"status": "success", "message": "Template saved"}
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.delete_template")
    def test_delete_template(self, mock_delete_template, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        mock_delete_template.return_value = True
        response = self.client.delete("/templates", json={"name": "template_to_delete"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"status": "success", "message": "Template deleted"}
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.render_template")
    def test_stream(self, mock_render_template, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        response = self.client.get("/stream")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with("stream.html")

    def test_api_discover(self):
        response = self.client.get("/api/discover")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("version", data)
        self.assertIn("endpoints", data)
        self.assertIsInstance(data["endpoints"], list)
        self.assertTrue(len(data["endpoints"]) > 0)
        for endpoint in data["endpoints"]:
            self.assertIn("path", endpoint)
            self.assertIn("method", endpoint)
            self.assertIn("description", endpoint)
            self.assertIn("authentication_required", endpoint)

    @patch("app.routes.SessionLocal")
    @patch("app.routes.camera_discovery.discover_cameras")
    @patch("app.routes.render_template")
    def test_discover_route(
        self, mock_render_template, mock_discover, mock_session_local
    ):
        mock_discover.return_value = [
            {"ip": "1.2.3.4", "protocol": "rtsp", "port": 554, "info": {}}
        ]
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
        response = self.client.get("/discover")
        self.assertEqual(response.status_code, 200)
        mock_discover.assert_not_called()
        mock_render_template.assert_called_with("discover.html", cameras=[])

    @patch("app.routes.SessionLocal")
    @patch("app.routes.camera_discovery.discover_cameras")
    def test_discover_scan(self, mock_discover, mock_session_local):
        mock_discover.return_value = [
            {"ip": "1.2.3.4", "protocol": "rtsp", "port": 554, "info": {}}
        ]
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
        response = self.client.post("/discover/scan")
        self.assertEqual(response.status_code, 200)
        mock_discover.assert_called_once()
        self.assertEqual(response.get_json(), mock_discover.return_value)

    @patch("app.routes.SessionLocal")
    @patch("app.routes.template_manager.save_template")
    def test_discover_add(self, mock_save_template, mock_session_local):
        mock_save_template.return_value = True
        payload = {"name": "cam", "ip": "1.2.3.4", "protocol": "rtsp", "port": 554}
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
        response = self.client.post("/discover/add", json=payload)
        self.assertEqual(response.status_code, 200)
        mock_save_template.assert_called()


if __name__ == "__main__":
    unittest.main()
