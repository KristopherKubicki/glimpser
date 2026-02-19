from __future__ import annotations

import pytest

from app.utils import eufy_cloud


def test_parse_eufy_url_profile_and_device() -> None:
    profile, device_id = eufy_cloud.parse_eufy_url("eufy://argyle/abc123")
    assert profile == "argyle"
    assert device_id == "abc123"


def test_parse_eufy_url_compact_default_profile() -> None:
    profile, device_id = eufy_cloud.parse_eufy_url("eufy://device_xyz")
    assert profile == "default"
    assert device_id == "device_xyz"


def test_snapshot_token_roundtrip() -> None:
    token = eufy_cloud.issue_snapshot_token("beach", "device001")
    assert token
    assert eufy_cloud.verify_snapshot_token(token) == ("beach", "device001")


def test_snapshot_token_invalid() -> None:
    assert eufy_cloud.verify_snapshot_token("not-a-valid-token") is None


def test_configured_native_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "argyle": {
                "mode": "native",
                "native_email": "guest@example.com",
                "native_password": "secret",
            }
        },
    )

    assert eufy_cloud.configured("argyle") is True


def test_list_devices_native_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "argyle": {
                "mode": "native",
                "native_email": "guest@example.com",
                "native_password": "secret",
            }
        },
    )

    def _fake_native_request(profile, endpoint, *, payload=None, timeout=0, retry=True):
        assert profile.name == "argyle"
        assert endpoint == "v2/app/get_devs_list"
        assert payload is None
        assert retry is True
        return {
            "code": 0,
            "data": [
                {
                    "device_sn": "dev-1",
                    "device_name": "Back Door",
                    "device_model": "T8410",
                    "station_sn": "station-1",
                    "cover_path": "https://cdn.example.test/a.jpg",
                    "status": 1,
                }
            ],
        }

    monkeypatch.setattr(eufy_cloud, "_native_request", _fake_native_request)

    devices = eufy_cloud.list_devices("argyle")
    assert devices == [
        {
            "device_id": "dev-1",
            "model": "T8410",
            "name": "Back Door",
            "online": True,
            "snapshot": True,
            "station": "station-1",
        }
    ]


def test_fetch_snapshot_native_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "argyle": {
                "mode": "native",
                "native_email": "guest@example.com",
                "native_password": "secret",
            }
        },
    )

    def _fake_native_request(profile, endpoint, *, payload=None, timeout=0, retry=True):
        assert profile.name == "argyle"
        assert endpoint == "v2/app/get_devs_list"
        return {
            "code": 0,
            "data": [
                {
                    "device_sn": "dev-2",
                    "device_name": "Front",
                    "cover_path": "https://cdn.example.test/front.jpg",
                }
            ],
        }

    seen: dict[str, object] = {}

    def _fake_native_fetch_image(profile, image_url, *, timeout):
        seen["profile"] = profile.name
        seen["url"] = image_url
        seen["timeout"] = timeout
        return b"jpeg-bytes", "image/jpeg"

    monkeypatch.setattr(eufy_cloud, "_native_request", _fake_native_request)
    monkeypatch.setattr(eufy_cloud, "_native_fetch_image", _fake_native_fetch_image)

    payload, content_type = eufy_cloud.fetch_snapshot("argyle", "dev-2", timeout=9)
    assert payload == b"jpeg-bytes"
    assert content_type == "image/jpeg"
    assert seen == {
        "profile": "argyle",
        "timeout": 9,
        "url": "https://cdn.example.test/front.jpg",
    }


def test_native_session_sets_captcha_challenge(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="argyle",
        mode="native",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="guest@example.com",
        native_password="secret",
        native_country="US",
    )

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "code": 100032,
                "msg": "Failed to request.",
                "data": {
                    "captcha_id": "cid-123",
                    "item": "data:image/png;base64,abc",
                },
            }

    eufy_cloud._clear_native_session(profile.name)
    eufy_cloud.clear_native_captcha(profile.name)
    monkeypatch.setattr(eufy_cloud, "_native_api_base", lambda *a, **k: "https://x")
    monkeypatch.setattr(eufy_cloud.requests, "post", lambda *a, **k: _FakeResp())

    with pytest.raises(eufy_cloud.EufyCaptchaRequired):
        eufy_cloud._native_session(profile, timeout=1, force_login=True)

    challenge = eufy_cloud.get_native_captcha(profile.name)
    assert challenge is not None
    assert challenge["captcha_id"] == "cid-123"
    assert challenge["captcha_item"].startswith("data:image/png;base64,")

    eufy_cloud.clear_native_captcha(profile.name)
    eufy_cloud._clear_native_session(profile.name)


def test_submit_native_captcha_reuses_pending_challenge(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="argyle",
        mode="native",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="guest@example.com",
        native_password="secret",
        native_country="US",
    )
    monkeypatch.setattr(
        eufy_cloud,
        "resolve_profile",
        lambda name="default": profile if name == "argyle" else None,
    )

    eufy_cloud._set_native_captcha("argyle", "cid-1", "data:image/png;base64,abc")
    seen: dict[str, object] = {}

    def _fake_native_session(
        prof,
        *,
        timeout,
        force_login=False,
        captcha_id="",
        captcha_code="",
    ):
        seen["profile"] = prof.name
        seen["timeout"] = timeout
        seen["force_login"] = force_login
        seen["captcha_id"] = captcha_id
        seen["captcha_code"] = captcha_code
        eufy_cloud.clear_native_captcha(prof.name)
        return "token", "https://api.example", b"k" * 32, {}

    monkeypatch.setattr(eufy_cloud, "_native_session", _fake_native_session)

    eufy_cloud.submit_native_captcha("argyle", "4321", timeout=7)

    assert seen == {
        "profile": "argyle",
        "timeout": 7,
        "force_login": True,
        "captcha_id": "cid-1",
        "captcha_code": "4321",
    }
    assert eufy_cloud.get_native_captcha("argyle") is None


def test_submit_native_captcha_requires_pending_challenge(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="argyle",
        mode="native",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="guest@example.com",
        native_password="secret",
        native_country="US",
    )
    monkeypatch.setattr(
        eufy_cloud,
        "resolve_profile",
        lambda name="default": profile if name == "argyle" else None,
    )
    eufy_cloud.clear_native_captcha("argyle")

    with pytest.raises(eufy_cloud.EufyCloudError):
        eufy_cloud.submit_native_captcha("argyle", "1234")
