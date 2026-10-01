from unittest.mock import patch

import pytest
from flask import Flask

from app.blueprints.ui import create_blueprint


@pytest.fixture(autouse=True)
def private_live_allowlist(monkeypatch):
    monkeypatch.setattr(
        "app.blueprints.ui.VIEWER_CONFIG", {"google_live_cameras": ["ExampleDoor"]}
    )


def client():
    app = Flask(__name__)
    app.secret_key = "test"
    with patch("app.routes.login_required", lambda f: f):
        app.register_blueprint(create_blueprint())
    return app.test_client()


def test_live_config_restricts_names_and_private_cameras():
    c = client()
    assert c.get("/kiosk_live_config?camera=Other").status_code == 404
    with patch(
        "app.routes.template_manager.get_template",
        return_value={"private_camera": True},
    ):
        assert c.get("/kiosk_live_config?camera=ExampleDoor").status_code == 403


def test_live_config_issues_camera_scoped_token_without_credentials():
    c = client()
    with (
        patch(
            "app.routes.template_manager.get_template",
            return_value={"url": "sdm://example-home/door-id"},
        ),
        patch(
            "app.utils.google_sdm.issue_webrtc_preview_token", return_value="signed"
        ) as sign,
    ):
        response = c.get("/kiosk_live_config?camera=ExampleDoor")
    assert response.status_code == 200
    assert response.json == {
        "profile": "example-home",
        "device_id": "door-id",
        "token": "signed",
    }
    assert response.headers["Cache-Control"] == "no-store"
    sign.assert_called_once_with("example-home", "door-id")


def test_heartbeat_is_scoped_to_address_and_profile():
    c = client()
    assert c.get("/kiosk_health?profile=office").json["age_seconds"] is None
    assert c.post("/kiosk_health?profile=office").status_code == 204
    assert c.get("/kiosk_health?profile=office").json["age_seconds"] < 1
    assert c.get("/kiosk_health?profile=living").json["age_seconds"] is None
    assert (
        c.get(
            "/kiosk_health?profile=office",
            environ_overrides={"REMOTE_ADDR": "192.0.2.1"},
        ).json["age_seconds"]
        is None
    )
    assert c.post("/kiosk_health?profile=bad").status_code == 400


def test_rtsp_router_mapping_preserves_snapshot_url_and_auth():
    from app.routes import resolve_live_stream_url

    details = {
        "url": "http://user:pass@camera.example:9008/ISAPI/Streaming/channels/901/picture"
    }
    with patch(
        "app.routes.config.get_setting", return_value='{"camera.example:9008":9010}'
    ):
        result = resolve_live_stream_url(details, "sub")
    assert "user:pass@camera.example:9010/Streaming/Channels/902" in result
    assert ":9008/" in details["url"]


def test_invalid_rtsp_mapping_falls_back_without_crashing():
    from app.routes import resolve_live_stream_url

    details = {"url": "http://camera.example:9008/ISAPI/Streaming/channels/901/picture"}
    with patch(
        "app.routes.config.get_setting",
        return_value='{"camera.example:9008":"invalid"}',
    ):
        assert ":9008/" in resolve_live_stream_url(details)


def test_kiosk_quality_caps_resolution_and_keeps_three_fps():
    from app.blueprints.stream import create_blueprint as stream_blueprint

    app = Flask(__name__)
    with patch("app.routes.login_required", lambda f: f):
        app.register_blueprint(stream_blueprint())
    with (
        patch(
            "app.routes.template_manager.get_template",
            return_value={"url": "rtsp://camera.invalid/live"},
        ),
        patch("app.routes.live_host_key", return_value=""),
        patch("app.routes.preflight_live_url", return_value=(True, {})),
        patch("app.routes.config.LIVE_RTSP_WIDTH", 1280),
        patch("app.routes.config.LIVE_RTSP_FPS", 10),
        patch(
            "app.routes.generate_warm_live_stream", return_value=iter([b"test"])
        ) as generate,
    ):
        response = app.test_client().get(
            "/live_video?camera=Driveway&quality=kiosk&profile=main"
        )
        assert response.status_code == 200
        assert response.data == b"test"
        assert response.headers["X-Live-Quality"] == "kiosk"
        generate.assert_called_once_with("rtsp://camera.invalid/live", width=960, fps=3)


def test_live_config_keeps_existing_authentication_boundary():
    app = Flask(__name__)
    app.secret_key = "test"
    app.add_url_rule("/login", endpoint="login", view_func=lambda: "login")
    app.register_blueprint(create_blueprint())
    with (
        patch("app.routes.config.SKIP_LOGIN_SUBNETS", []),
        patch("app.routes.API_KEY", "test-key"),
    ):
        response = app.test_client().get(
            "/kiosk_live_config?camera=ExampleDoor",
            environ_overrides={"REMOTE_ADDR": "203.0.113.1"},
        )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
