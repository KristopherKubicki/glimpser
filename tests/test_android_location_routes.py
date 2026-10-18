from unittest.mock import patch

from flask import Flask

from app.blueprints.location import create_blueprint


def _test_app() -> Flask:
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.register_blueprint(create_blueprint())
    return app


def _setting(name: str, default: str = "") -> str:
    if name == "ANDROID_LOCATION_TOKEN":
        return "loc-secret"
    return default


def test_android_location_ingest_accepts_bearer_token() -> None:
    app = _test_app()
    with (
        patch("app.routes.config.get_setting", side_effect=_setting),
        patch(
            "app.blueprints.location.location_bridge.save_latest_location",
            return_value={
                "subject_id": "phone-k",
                "label": "K Phone",
                "provider": "android",
                "latitude": 42.0,
                "longitude": -87.7,
            },
        ) as save_latest,
    ):
        response = app.test_client().post(
            "/integrations/android/location",
            headers={"Authorization": "Bearer loc-secret"},
            json={"device_id": "phone-k", "latitude": 42, "longitude": -87.7},
        )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    save_latest.assert_called_once()


def test_android_location_ingest_rejects_missing_token() -> None:
    app = _test_app()
    with patch("app.routes.config.get_setting", side_effect=_setting):
        response = app.test_client().post(
            "/integrations/android/location",
            json={"device_id": "phone-k", "latitude": 42, "longitude": -87.7},
        )

    assert response.status_code == 401
    assert response.get_json() == {"ok": False, "error": "unauthorized"}


def test_android_location_ingest_reports_payload_errors() -> None:
    app = _test_app()
    with patch("app.routes.config.get_setting", side_effect=_setting):
        response = app.test_client().post(
            "/integrations/android/location",
            headers={"X-Location-Token": "loc-secret"},
            json={"device_id": "bad", "latitude": 120, "longitude": -87.7},
        )

    assert response.status_code == 400
    assert response.get_json()["ok"] is False
