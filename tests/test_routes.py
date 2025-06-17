import os
import sys
from unittest.mock import patch
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import Summary


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 302


def test_login_success(client, patch_session_local, reset_login_attempts, monkeypatch):
    monkeypatch.setattr("app.routes.check_password_hash", lambda h, p: True)
    response = client.post(
        "/login", data={"username": "testuser", "password": "testpassword"}
    )
    assert response.status_code == 302
    assert "/" in response.headers["Location"]


def test_login_failure(client, patch_session_local, reset_login_attempts):
    with patch("app.routes.check_password_hash", return_value=False), patch(
        "app.routes.render_template"
    ) as render:
        response = client.post(
            "/login", data={"username": "testuser", "password": "wrong"}
        )
        assert response.status_code == 200
        render.assert_called_with("login.html", page_title="Login")


def test_login_missing_fields(client, patch_session_local, reset_login_attempts):
    with patch("app.routes.render_template") as render:
        response = client.post("/login", data={"username": "", "password": ""})
        assert response.status_code == 400
        render.assert_called_with("login.html", page_title="Login")


def test_logout(client, patch_session_local, user_session):
    response = client.get("/logout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_index(client, patch_session_local, user_session):
    with patch(
        "app.routes.template_manager.get_templates", return_value={"camera": {}}
    ) as get_t, patch("app.routes.render_template") as render:
        response = client.get("/")
        assert response.status_code == 200
        render.assert_called_with(
            "index.html", template_details={"camera": {}}, page_title="Dashboard"
        )
        get_t.assert_called_once()


def test_captions(client, patch_session_local, user_session):
    with patch(
        "app.routes.template_manager.get_templates",
        return_value={"template1": {}, "template2": {}},
    ) as get_t, patch("app.routes.render_template") as render:
        response = client.get("/captions")
        assert response.status_code == 200
        render.assert_called_with(
            "captions.html",
            template_details=get_t.return_value,
            lcaptions=[],
            page_title="Captions",
        )


def test_get_templates(client, patch_session_local, user_session):
    with patch(
        "app.routes.template_manager.get_templates",
        return_value={"template1": {}, "template2": {}},
    ) as get_t:
        response = client.get("/templates?group=all")
        assert response.status_code == 200
        assert response.get_json() == get_t.return_value


def test_save_template(client, patch_session_local, user_session):
    with patch(
        "app.routes.template_manager.save_template", return_value=True
    ) as save_t:
        response = client.post(
            "/templates", json={"name": "new_template", "url": "http://example.com"}
        )
        assert response.status_code == 200
        assert response.get_json() == {"status": "success", "message": "Template saved"}
        save_t.assert_called_once()


def test_delete_template(client, patch_session_local, user_session):
    with patch(
        "app.routes.template_manager.delete_template", return_value=True
    ) as delete_t:
        response = client.delete("/templates", json={"name": "template_to_delete"})
        assert response.status_code == 200
        assert response.get_json() == {
            "status": "success",
            "message": "Template deleted",
        }
        delete_t.assert_called_once()


def test_stream(client, patch_session_local, user_session):
    with patch("app.routes.render_template") as render:
        response = client.get("/stream")
        assert response.status_code == 200
        render.assert_called_with("stream.html", page_title="Stream")


def test_api_discover(client):
    response = client.get("/api/discover")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    assert "version" in data
    assert "endpoints" in data and isinstance(data["endpoints"], list)
    assert len(data["endpoints"]) > 0
    for endpoint in data["endpoints"]:
        assert {
            "path",
            "method",
            "description",
            "authentication_required",
        } <= endpoint.keys()


def test_discover_route(client, patch_session_local, user_session):
    payload = {"name": "cam", "ip": "1.2.3.4", "protocol": "rtsp", "port": 554}
    with patch(
        "app.routes.camera_discovery.discover_cameras", return_value=[payload]
    ) as discover, patch("app.routes.render_template") as render:
        response = client.get("/discover")
        assert response.status_code == 200
        render.assert_called_with(
            "discover.html", cameras=[], page_title="Discover Cameras"
        )

        response = client.post("/discover/scan")
        assert response.status_code == 200
        discover.assert_called()
        assert response.get_json() == discover.return_value

    with patch(
        "app.routes.template_manager.save_template", return_value=True
    ) as save_t:
        response = client.post("/discover/add", json=payload)
        assert response.status_code == 200
        save_t.assert_called()


def test_live_single_camera(client, patch_session_local, user_session):
    with patch(
        "app.routes.template_manager.get_template",
        return_value={"url": "https://example.com"},
    ) as get_t, patch("app.routes.render_template") as render:
        response = client.get("/live?camera=cam1")
        assert response.status_code == 200
        get_t.assert_called_with("cam1")
        render.assert_called_with(
            "live.html",
            template_details={"cam1": get_t.return_value},
            page_title="Live View",
        )


def test_group_page(client, user_session):
    with patch(
        "app.routes.get_active_groups", return_value=["group1", "group2"]
    ) as groups, patch("app.routes.render_template") as render:
        response = client.get("/group/group1")
        assert response.status_code == 200
        render.assert_called_with(
            "group.html", group_name="group1", page_title="Group – group1"
        )
        groups.assert_called_once()


def test_group_page_not_found(client, user_session):
    with patch("app.routes.get_active_groups", return_value=["group1"]) as groups:
        response = client.get("/group/unknown")
        assert response.status_code == 404
        groups.assert_called_once()


def test_group_page_all_redirect(client, user_session):
    with patch("app.routes.get_active_groups", return_value=["group1"]) as groups:
        response = client.get("/group/all")
        assert response.status_code == 302
        assert "/" in response.headers["Location"]
        groups.assert_called_once()


def test_groups_endpoint_includes_all(client, user_session):
    with patch("app.routes.get_active_groups", return_value=["group1"]) as groups:
        response = client.get("/groups")
        assert response.status_code == 200
        data = response.get_json()
        assert "all" in data
        groups.assert_called_once()


def test_captions_status(client, patch_session_local, user_session):
    class DummyQuery:
        def __init__(self, model):
            self.model = model

        def filter_by(self, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            if self.model is Summary:
                return SimpleNamespace(timestamp=0, content='{"summary":"hello"}')
            return SimpleNamespace(id=1)

    class DummySession:
        def query(self, model):
            return DummyQuery(model)

        def close(self):
            pass

    with patch("app.routes.SessionLocal", return_value=DummySession()):
        response = client.get("/captions_status")
        assert response.status_code == 200
        assert response.get_json() == {
            "caption": "hello",
            "timestamp": "1970-01-01 00:00:00",
        }
