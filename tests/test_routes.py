# tests/test_routes.py

import importlib
import os
import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from flask import Flask

from app import routes
from app.models import Summary
from app.utils.template_manager import clear_template_cache


class TestRoutes(unittest.TestCase):
    def setUp(self):
        importlib.reload(routes)

        template_dir = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "../app/templates"
        )
        self.app = Flask(__name__, template_folder=template_dir)
        self.app.config["SECRET_KEY"] = "my_secret_key"  # pragma: allowlist secret
        self.subnet_patch = patch("app.routes.config.SKIP_LOGIN_SUBNETS", [])
        self.subnet_patch.start()
        routes.init_routes(self.app)
        self.client = self.app.test_client()
        clear_template_cache()

    def tearDown(self):
        self.subnet_patch.stop()

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

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def all(self):
                return []

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.post(
            "/login",
            data={
                "username": "testuser",
                "password": "testpassword",  # pragma: allowlist secret
            },
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

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def all(self):
                return []

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.post(
            "/login",
            data={
                "username": "testuser",
                "password": "wrongpassword",  # pragma: allowlist secret
            },
        )
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "login.html", page_title="Login", show_recovery_note=True
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.login_attempts", {})
    @patch("app.routes.render_template")
    def test_login_missing_fields(self, mock_render_template, mock_session_local):
        response = self.client.post("/login", data={"username": "", "password": ""})
        self.assertEqual(response.status_code, 400)
        mock_render_template.assert_called_with(
            "login.html", page_title="Login", show_recovery_note=True
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    def test_logout(self, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def all(self):
                return []

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
    @patch("app.routes.template_manager.get_templates")
    def test_index(self, mock_get_templates, mock_render_template, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def all(self):
                return []

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        mock_get_templates.return_value = {"camera": {}}
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "index.html", template_details={"camera": {}}, page_title="Dashboard"
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.get_templates")
    @patch("app.blueprints.ui.render_template")
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
            latest_caption="",
            page_title="Captions",
            cost_start=None,
            cost_end=None,
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
    @patch("app.routes.camera_discovery.autodetect_onvif_endpoints", return_value={})
    @patch("app.routes.template_manager.save_template")
    def test_save_template(self, mock_save_template, _auto, mock_session_local):
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
    @patch("app.blueprints.ui.render_template")
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
        mock_render_template.assert_called_with("stream.html", page_title="Stream")

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
    @patch("app.routes.template_manager.get_templates")
    @patch("app.routes.render_template")
    def test_discover_route(
        self,
        mock_render_template,
        mock_get_templates,
        mock_discover,
        mock_session_local,
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
        mock_get_templates.return_value = {}

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
        response = self.client.get("/discover")
        self.assertEqual(response.status_code, 200)
        mock_discover.assert_not_called()
        mock_render_template.assert_called_with(
            "discover.html",
            cameras=[],
            existing_urls={},
            object_tokens=mock.ANY,
            clip_model=mock.ANY,
            clip_gpu=mock.ANY,
            page_title="Discover Cameras",
        )

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

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.get_template")
    @patch("app.blueprints.ui.render_template")
    def test_live_single_camera(
        self, mock_render_template, mock_get_template, mock_session_local
    ):
        """The live route should render only the requested camera."""

        mock_get_template.return_value = {"url": "https://example.com"}

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return SimpleNamespace(id=1)

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.get("/live?camera=cam1")
        self.assertEqual(response.status_code, 200)
        mock_get_template.assert_called_with("cam1")
        mock_render_template.assert_called_with(
            "live.html",
            template_details={
                "cam1": {
                    **mock_get_template.return_value,
                    "capabilities": {
                        "kind": "web",
                        "live_video": False,
                        "avg_ttfb_ms": 0,
                        "last_ttfb_ms": 0,
                        "avoid_for_s": 0,
                        "source": "url",
                    },
                }
            },
            selected_camera="cam1",
            selected_group=None,
            page_title="Live View",
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    @patch("app.routes.template_manager.get_templates")
    @patch("app.blueprints.ui.render_template")
    def test_live_group_filters_templates(
        self, mock_render_template, mock_get_templates, mock_session_local
    ):
        """The live route should honor an explicit group selection."""

        mock_get_templates.return_value = {
            "cam1": {"groups": "g1, g2"},
            "cam2": {"groups": "g2"},
            "cam3": {"groups": "other"},
        }

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return SimpleNamespace(id=1)

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.get("/live?group=g2")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "live.html",
            template_details={
                "cam1": {
                    "groups": "g1, g2",
                    "capabilities": {"kind": "unknown", "live_video": False},
                },
                "cam2": {
                    "groups": "g2",
                    "capabilities": {"kind": "unknown", "live_video": False},
                },
            },
            selected_camera=None,
            selected_group="g2",
            page_title="Live View",
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.render_template")
    @patch("app.routes.get_active_groups")
    @patch("app.routes.session", {"user_id": 1})
    def test_group_page(self, mock_groups, mock_render_template, mock_session_local):
        mock_groups.return_value = ["group1", "group2"]
        response = self.client.get("/group/group1")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "group.html", group_name="group1", page_title="Group – group1"
        )

    @patch("app.routes.SessionLocal")
    @patch("app.routes.get_active_groups")
    @patch("app.routes.session", {"user_id": 1})
    def test_group_page_not_found(self, mock_groups, mock_session_local):
        mock_groups.return_value = ["group1"]
        response = self.client.get("/group/unknown")
        self.assertEqual(response.status_code, 404)

    @patch("app.routes.SessionLocal")
    @patch("app.routes.get_active_groups")
    @patch("app.routes.session", {"user_id": 1})
    def test_group_page_all_redirect(self, mock_groups, mock_session_local):
        mock_groups.return_value = ["group1"]
        response = self.client.get("/group/all")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/", response.headers["Location"])

    @patch("app.routes.SessionLocal")
    @patch("app.routes.get_active_groups")
    @patch("app.routes.session", {"user_id": 1})
    def test_groups_endpoint_includes_all(self, mock_groups, mock_session_local):
        mock_groups.return_value = ["group1"]
        response = self.client.get("/groups")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("all", data)

    @patch("app.routes.SessionLocal")
    @patch("app.routes.session", {"user_id": 1})
    def test_captions_status(self, mock_session_local):
        dummy_user = SimpleNamespace(id=1)

        class DummyQuery:
            def __init__(self, model):
                self.model = model
                self.order_called = False

            def filter_by(self, **kwargs):
                self.filter_kwargs = kwargs
                return self

            def order_by(self, *args, **kwargs):
                self.order_called = True
                return self

            def first(self):
                if self.model is Summary:
                    return SimpleNamespace(timestamp=0, content='{"summary":"hello"}')
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery(model)

            def close(self):
                pass

        mock_session_local.return_value = DummySession()

        response = self.client.get("/captions_status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("caption", data)
        self.assertIn("timestamp", data)


if __name__ == "__main__":
    unittest.main()
