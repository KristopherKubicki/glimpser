import unittest
import os
import sys
from unittest.mock import patch
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'my_secret_key'
        init_routes(self.app)
        self.client = self.app.test_client()

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "healthy"})

    @patch("app.routes.check_password_hash")
    @patch("app.routes.USER_NAME", "testuser")
    def test_login_success(self, mock_check_password):
        mock_check_password.return_value = True
        response = self.client.post(
            "/login", data={"username": "testuser", "password": "testpassword"}
        )
        self.assertEqual(response.status_code, 302)  # Redirect status code
        self.assertIn("/", response.headers["Location"])

    @patch("app.routes.check_password_hash")
    @patch("app.routes.USER_NAME", "testuser")
    def test_login_failure(self, mock_check_password):
        mock_check_password.return_value = False
        response = self.client.post(
            "/login", data={"username": "testuser", "password": "wrongpassword"}
        )
        self.assertEqual(response.status_code, 302)  # Redirect status code
        self.assertIn("/login", response.headers["Location"])
        self.assertIn(b"Invalid username or password", response.data)

    @patch("app.routes.session")
    def test_logout(self, mock_session):
        with self.client as c:
            with c.session_transaction() as sess:
                sess['logged_in'] = True
            response = c.get("/logout")
            self.assertEqual(response.status_code, 302)  # Redirect status code
            self.assertIn("/login", response.headers["Location"])
            mock_session.pop.assert_called_with("logged_in", None)

    @patch("app.routes.login_required")
    @patch("app.routes.render_template")
    def test_index(self, mock_render_template, mock_login_required):
        mock_login_required.return_value = lambda x: x
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with("index.html")

    @patch("app.routes.login_required")
    @patch("app.routes.template_manager.get_templates")
    @patch("app.routes.render_template")
    def test_captions(
        self, mock_render_template, mock_get_templates, mock_login_required
    ):
        mock_login_required.return_value = lambda x: x
        mock_get_templates.return_value = {"template1": {}, "template2": {}}
        response = self.client.get("/captions")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "captions.html",
            template_details=mock_get_templates.return_value,
            lcaptions=[],
        )

    @patch("app.routes.login_required")
    @patch("app.routes.template_manager.get_templates")
    def test_get_templates(self, mock_get_templates, mock_login_required):
        mock_login_required.return_value = lambda x: x
        mock_get_templates.return_value = {"template1": {}, "template2": {}}
        response = self.client.get("/templates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"template1": {}, "template2": {}})

    @patch("app.routes.login_required")
    @patch("app.routes.template_manager.save_template")
    def test_save_template(self, mock_save_template, mock_login_required):
        mock_login_required.return_value = lambda x: x
        mock_save_template.return_value = True
        response = self.client.post(
            "/templates", json={"name": "new_template", "url": "http://example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json, {"status": "success", "message": "Template saved"}
        )

    @patch("app.routes.login_required")
    @patch("app.routes.template_manager.delete_template")
    def test_delete_template(self, mock_delete_template, mock_login_required):
        mock_login_required.return_value = lambda x: x
        mock_delete_template.return_value = True
        response = self.client.delete("/templates", json={"name": "template_to_delete"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json, {"status": "success", "message": "Template deleted"}
        )

    @patch("app.routes.login_required")
    @patch("app.routes.render_template")
    def test_stream(self, mock_render_template, mock_login_required):
        mock_login_required.return_value = lambda x: x
        response = self.client.get("/stream")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with("stream.html")


if __name__ == "__main__":
    unittest.main()
