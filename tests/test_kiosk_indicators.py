import io
import json
from unittest.mock import patch

import pytest
from flask import Flask

from app.blueprints.ui import create_blueprint
from app.utils import kiosk_indicators as indicators

NOW = 1800000000


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(indicators, "PRIVACY_URL", "https://privacy.example/status")
    monkeypatch.setattr(indicators, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(indicators, "TOKEN", tmp_path / "token")
    indicators.TOKEN.write_text("test-key")
    monkeypatch.setattr(indicators, "_PRIVACY", {"checked": 0, "value": "unknown"})


def test_unconfigured_privacy_makes_no_network_request(monkeypatch):
    monkeypatch.setattr(indicators, "PRIVACY_URL", "")
    with patch.object(indicators, "urlopen") as request:
        assert indicators.snapshot("office", NOW)["privacy"] == "unknown"
    request.assert_not_called()


def event(kind="door", ident="door:1", at=NOW):
    return {"id": ident, "kind": kind, "at": at * 1000, "label": "Front Door"}


def test_dedup_restart_expiry_and_content_minimization():
    indicators.accept(event(), NOW)
    indicators.accept(event(), NOW + 1)
    indicators.accept(event("sms", "sms:2"), NOW + 1)
    value = indicators.snapshot("living", NOW + 2)
    assert len(value["events"]) == 2
    assert value["events"][1] == {"id": "sms:2", "kind": "sms", "at": NOW}
    assert "privacy" not in value
    assert indicators.snapshot("living", NOW + 11)["events"] == []
    assert indicators.snapshot("living", NOW + 91)["available"] is False
    indicators.accept(event("heartbeat", "heartbeat:3", NOW + 92), NOW + 92)
    assert indicators.snapshot("living", NOW + 92) == {
        "server_time": NOW + 92,
        "available": True,
        "events": [],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"at": (NOW - 16) * 1000},
        {"at": (NOW + 6) * 1000},
        {"body": "private sms"},
        {"kind": "all_clear"},
        {"label": "x" * 101},
        {"at": float("nan")},
    ],
)
def test_invalid_payload_rejected(change):
    with pytest.raises(ValueError):
        indicators.accept(event() | change, NOW)


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"available": True, "active": True, "updated_ts": NOW}, "active"),
        ({"available": True, "active": False, "updated_ts": NOW}, "inactive"),
        ({"available": False, "active": False, "updated_ts": NOW}, "unknown"),
        ({"available": True, "active": False, "updated_ts": NOW - 121}, "unknown"),
        ({"available": True, "active": "false", "updated_ts": NOW}, "unknown"),
    ],
)
def test_privacy_requires_explicit_fresh_reading(data, expected):
    with patch.object(
        indicators, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())
    ):
        assert indicators.snapshot("office", NOW)["privacy"] == expected
    with patch.object(indicators, "urlopen", side_effect=OSError):
        assert indicators.snapshot("office", NOW + 3)["privacy"] == "unknown"


def test_route_security_profile_scoping_and_no_store():
    app = Flask(__name__)
    app.secret_key = "test"
    with patch("app.routes.login_required", lambda f: f):
        app.register_blueprint(create_blueprint())
    client = app.test_client()
    assert client.post("/kiosk_indicators", json=event()).status_code == 401
    with patch("app.blueprints.ui.time.time", return_value=NOW):
        assert (
            client.post(
                "/kiosk_indicators",
                json=event(),
                headers={"Authorization": "Bearer test-key"},
            ).status_code
            == 200
        )
        r = client.get("/kiosk_indicators?profile=living")
        assert r.status_code == 200 and "privacy" not in r.json
        assert r.headers["Cache-Control"] == "no-store"
        assert "test-key" not in r.text
    assert client.get("/kiosk_indicators?profile=other").status_code == 400
    assert (
        client.post(
            "/kiosk_indicators",
            data="x" * 2049,
            headers={"Authorization": "Bearer test-key"},
        ).status_code
        == 413
    )
