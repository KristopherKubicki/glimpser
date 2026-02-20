from __future__ import annotations

import pytest

from app.utils import eufy_cloud


@pytest.fixture(autouse=True)
def _allow_legacy_eufy_modes_for_tests(monkeypatch) -> None:
    """Keep legacy/native/webportal tests valid unless overridden per test."""

    monkeypatch.setattr(eufy_cloud, "_EUFY_EMULATOR_ONLY", False)


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


def test_configured_webportal_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "webportal",
                "native_email": "guest@example.com",
                "native_password": "secret",
                "webportal_url": "https://mysecurity.eufylife.com/#/camera",
            }
        },
    )

    assert eufy_cloud.configured("beach") is True


def test_configured_emulator_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "emulator",
                "emulator_devices_json": '{"devices":[{"device_id":"cam-1","name":"Driveway"}]}',
            }
        },
    )

    assert eufy_cloud.configured("beach") is True


def test_resolve_profile_maps_native_mode_to_webportal(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "legacy": {
                "mode": "native",
                "native_email": "guest@example.com",
                "native_password": "secret",
            }
        },
    )

    profile = eufy_cloud.resolve_profile("legacy")
    assert profile is not None
    assert profile.mode == "webportal"


def test_resolve_profile_supports_emulator_vm_alias(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "vm",
                "emulator_adb_serial": "emulator-5554",
                "emulator_devices_json": '[{"device_id":"cam-1","name":"Driveway"}]',
            }
        },
    )

    profile = eufy_cloud.resolve_profile("beach")
    assert profile is not None
    assert profile.mode == "emulator"
    assert profile.emulator_adb_serial == "emulator-5554"
    assert "cam-1" in profile.emulator_devices_json


def test_webportal_pin_backoff_roundtrip() -> None:
    profile = "beach"
    eufy_cloud.clear_webportal_pin_backoff(profile)
    assert eufy_cloud.get_webportal_pin_backoff_remaining(profile) == 0

    seconds = eufy_cloud._webportal_set_pin_backoff(profile)
    assert seconds > 0
    remaining = eufy_cloud.get_webportal_pin_backoff_remaining(profile)
    assert remaining > 0

    eufy_cloud.clear_webportal_pin_backoff(profile)
    assert eufy_cloud.get_webportal_pin_backoff_remaining(profile) == 0


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


def test_list_devices_emulator_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "emulator",
                "emulator_devices_json": """
                {
                  "devices": [
                    {"device_id":"cam-2","name":"Backyard","deep_link":"app://backyard"},
                    {"device_id":"cam-1","name":"Driveway"}
                  ]
                }
                """,
            }
        },
    )

    devices = eufy_cloud.list_devices("beach")
    assert [d["device_id"] for d in devices] == ["cam-2", "cam-1"]
    assert devices[0]["name"] == "Backyard"
    assert devices[1]["name"] == "Driveway"


def test_fetch_snapshot_native_mode(monkeypatch) -> None:
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
    monkeypatch.setattr(eufy_cloud, "resolve_profile", lambda name="default": profile)

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

    def _fake_native_session(profile, *, timeout, force_login=False, **_kwargs):
        assert profile.name == "argyle"
        assert timeout == 9
        assert force_login is False
        return "token", "https://api.example.test", b"k" * 32, {}

    monkeypatch.setattr(eufy_cloud, "_native_session", _fake_native_session)
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


def test_fetch_snapshot_webportal_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "webportal",
                "native_email": "guest@example.com",
                "native_password": "secret",
                "webportal_url": "https://mysecurity.eufylife.com/#/camera",
            }
        },
    )

    seen: dict[str, object] = {}

    def _fake_webportal_fetch(profile, device_id, *, timeout):
        seen["profile"] = profile.name
        seen["device_id"] = device_id
        seen["timeout"] = timeout
        return b"png-bytes", "image/png"

    monkeypatch.setattr(eufy_cloud, "_webportal_fetch_snapshot", _fake_webportal_fetch)

    payload, content_type = eufy_cloud.fetch_snapshot("beach", "dev-portal", timeout=11)
    assert payload == b"png-bytes"
    assert content_type == "image/png"
    assert seen == {"profile": "beach", "device_id": "dev-portal", "timeout": 11}


def test_fetch_snapshot_emulator_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "emulator",
                "emulator_adb_serial": "emulator-5554",
                "emulator_settle_seconds": 1,
                "emulator_devices_json": """
                [{"device_id":"cam-1","name":"Driveway","deep_link":"app://driveway"}]
                """,
            }
        },
    )

    calls: list[list[str]] = []

    class _FakeProc:
        def __init__(
            self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0
        ):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    def _fake_run(args, **_kwargs):
        calls.append(list(args))
        if "screencap" in args:
            return _FakeProc(stdout=b"\x89PNG\r\n\x1a\nfake")
        return _FakeProc(stdout=b"ok")

    monkeypatch.setattr(eufy_cloud.shutil, "which", lambda _cmd: "adb")
    monkeypatch.setattr(eufy_cloud.subprocess, "run", _fake_run)
    monkeypatch.setattr(eufy_cloud.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(eufy_cloud, "_emulator_ensure_ready", lambda *_a, **_k: None)

    payload, content_type = eufy_cloud.fetch_snapshot("beach", "cam-1", timeout=5)
    assert payload.startswith(b"\x89PNG")
    assert content_type == "image/png"
    assert calls[0][:4] == [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
    ]
    assert calls[1][-3:] == ["exec-out", "screencap", "-p"]


def test_fetch_snapshot_emulator_mode_uses_custom_adb_path(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "emulator",
                "emulator_adb_path": "/tmp/custom-adb",
                "emulator_adb_serial": "emulator-5554",
                "emulator_devices_json": """
                [{"device_id":"cam-1","name":"Driveway","deep_link":"app://driveway"}]
                """,
            }
        },
    )

    calls: list[list[str]] = []

    class _FakeProc:
        def __init__(
            self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0
        ):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    def _fake_run(args, **_kwargs):
        calls.append(list(args))
        if "screencap" in args:
            return _FakeProc(stdout=b"\x89PNG\r\n\x1a\nfake")
        return _FakeProc(stdout=b"ok")

    monkeypatch.setattr(eufy_cloud.subprocess, "run", _fake_run)
    monkeypatch.setattr(eufy_cloud.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(eufy_cloud, "_emulator_ensure_ready", lambda *_a, **_k: None)

    payload, content_type = eufy_cloud.fetch_snapshot("beach", "cam-1", timeout=5)
    assert payload.startswith(b"\x89PNG")
    assert content_type == "image/png"
    assert calls[0][0] == "/tmp/custom-adb"
    assert calls[1][0] == "/tmp/custom-adb"


def test_fetch_snapshot_emulator_falls_back_to_webportal_when_adb_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(eufy_cloud, "_EUFY_EMULATOR_WEBPORTAL_FALLBACK", True)
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "emulator",
                "native_email": "guest@example.com",
                "native_password": "secret",
                "webportal_url": "https://mysecurity.eufylife.com/#/camera",
                "emulator_devices_json": """
                [{"device_id":"cam-1","name":"Driveway","deep_link":"app://driveway"}]
                """,
            }
        },
    )

    monkeypatch.setattr(
        eufy_cloud,
        "_emulator_open_device",
        lambda *_a, **_k: (_ for _ in ()).throw(
            eufy_cloud.EufyCloudError("ADB executable not found")
        ),
    )
    monkeypatch.setattr(eufy_cloud, "_emulator_ensure_ready", lambda *_a, **_k: None)
    seen: dict[str, object] = {}

    def _fake_webportal_fetch(profile, device_id, *, timeout):
        seen["profile"] = profile.name
        seen["device_id"] = device_id
        seen["timeout"] = timeout
        return b"png-fallback", "image/png"

    monkeypatch.setattr(eufy_cloud, "_webportal_fetch_snapshot", _fake_webportal_fetch)

    payload, content_type = eufy_cloud.fetch_snapshot("beach", "cam-1", timeout=7)
    assert payload == b"png-fallback"
    assert content_type == "image/png"
    assert seen == {"profile": "beach", "device_id": "cam-1", "timeout": 7}


def test_emulator_ensure_ready_runs_boot_command(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="emulator",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="",
        native_password="",
        native_country="US",
        emulator_boot_cmd="vmctl start glimpser-android",
        emulator_boot_timeout_seconds=20.0,
    )

    states = iter([False, False, False, False, True])
    monkeypatch.setattr(eufy_cloud, "_emulator_adb_ready", lambda _p: next(states))
    monkeypatch.setattr(eufy_cloud.time, "sleep", lambda *_a, **_k: None)

    commands: list[object] = []

    class _Proc:
        returncode = 0
        stdout = b""
        stderr = b""

    def _fake_run(cmd, **_kwargs):
        commands.append(cmd)
        return _Proc()

    monkeypatch.setattr(eufy_cloud, "_emulator_run_command", _fake_run)
    monkeypatch.setattr(eufy_cloud, "_emulator_adb_prefix", lambda _p: ["adb"])

    eufy_cloud._emulator_ensure_ready(profile, timeout=8)
    assert commands[0] == ["adb", "start-server"]
    assert commands[1] == ["adb", "connect", "127.0.0.1:5555"]
    assert commands[2] == "vmctl start glimpser-android"


def test_emulator_ensure_ready_requires_boot_command(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="emulator",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="",
        native_password="",
        native_country="US",
    )
    monkeypatch.setattr(eufy_cloud, "_emulator_adb_ready", lambda _p: False)
    monkeypatch.setattr(
        eufy_cloud,
        "_emulator_run_command",
        lambda *_a, **_k: type(
            "P", (), {"returncode": 0, "stdout": b"", "stderr": b""}
        )(),
    )
    monkeypatch.setattr(eufy_cloud, "_emulator_adb_prefix", lambda _p: ["adb"])

    with pytest.raises(eufy_cloud.EufyCloudError, match="Boot Command"):
        eufy_cloud._emulator_ensure_ready(profile, timeout=5)


def test_emulator_guess_boot_cmd_prefers_env(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="emulator",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="",
        native_password="",
        native_country="US",
    )
    monkeypatch.setenv("GLIMPSER_EUFY_BOOT_CMD", "custom-start-cmd")
    assert eufy_cloud._emulator_guess_boot_cmd(profile) == "custom-start-cmd"


def test_emulator_guess_boot_cmd_uses_virsh_domain(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="emulator",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="",
        native_password="",
        native_country="US",
    )

    monkeypatch.delenv("GLIMPSER_EUFY_BOOT_CMD", raising=False)
    monkeypatch.setattr(
        eufy_cloud.shutil,
        "which",
        lambda cmd: "/usr/bin/virsh" if cmd == "virsh" else "",
    )

    class _Proc:
        returncode = 0
        stderr = b""
        stdout = b"test-vm\nandroid-eufy\n"

    monkeypatch.setattr(eufy_cloud.subprocess, "run", lambda *_a, **_k: _Proc())
    boot_cmd = eufy_cloud._emulator_guess_boot_cmd(profile)
    assert boot_cmd.endswith(" start android-eufy")


def test_emulator_try_adb_connect_uses_serial_target(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="emulator",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="",
        native_password="",
        native_country="US",
        emulator_adb_serial="192.168.2.95:5555",
    )

    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = b""
        stderr = b""

    def _fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return _Proc()

    states = iter([True])
    monkeypatch.setattr(eufy_cloud, "_emulator_adb_ready", lambda _p: next(states))
    monkeypatch.setattr(eufy_cloud, "_emulator_run_command", _fake_run)
    monkeypatch.setattr(eufy_cloud, "_emulator_adb_prefix", lambda _p: ["adb"])

    assert eufy_cloud._emulator_try_adb_connect(profile) is True
    assert calls[0] == ["adb", "connect", "192.168.2.95:5555"]


def test_emulator_only_forces_non_emulator_profiles(monkeypatch) -> None:
    monkeypatch.setattr(eufy_cloud, "_EUFY_EMULATOR_ONLY", True)
    monkeypatch.setattr(
        eufy_cloud,
        "_load_profiles",
        lambda: {
            "beach": {
                "mode": "webportal",
                "native_email": "guest@example.com",
                "native_password": "secret",
                "webportal_url": "https://mysecurity.eufylife.com/#/camera",
                "emulator_devices_json": '[{"device_id":"cam-1","name":"Driveway"}]',
            }
        },
    )

    profile = eufy_cloud.resolve_profile("beach")
    assert profile is not None
    assert profile.mode == "emulator"


def test_fetch_snapshot_native_falls_back_to_webportal(monkeypatch) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="native",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="guest@example.com",
        native_password="secret",
        native_country="US",
        webportal_url="https://mysecurity.eufylife.com/#/camera",
    )
    monkeypatch.setattr(eufy_cloud, "resolve_profile", lambda name="default": profile)

    monkeypatch.setattr(
        eufy_cloud,
        "_native_fetch_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            eufy_cloud.EufyCloudError(
                "Eufy cloud device 'x' has no usable snapshot or stream URL in API response"
            )
        ),
    )

    seen: dict[str, object] = {}

    def _fake_webportal_fetch(profile, device_id, *, timeout):
        seen["profile"] = profile.name
        seen["device_id"] = device_id
        seen["timeout"] = timeout
        return b"png-fallback", "image/png"

    monkeypatch.setattr(eufy_cloud, "_webportal_fetch_snapshot", _fake_webportal_fetch)

    payload, content_type = eufy_cloud.fetch_snapshot(
        "beach", "dev-fallback", timeout=8
    )
    assert payload == b"png-fallback"
    assert content_type == "image/png"
    assert seen == {"profile": "beach", "device_id": "dev-fallback", "timeout": 8}


def test_fetch_snapshot_native_does_not_fallback_on_unrelated_error(
    monkeypatch,
) -> None:
    profile = eufy_cloud.EufyCloudProfile(
        name="beach",
        mode="native",
        bridge_url="",
        api_token="",
        devices_path="/api/devices",
        snapshot_path="/api/cameras/{device_id}/snapshot",
        verify_tls=True,
        native_email="guest@example.com",
        native_password="secret",
        native_country="US",
        webportal_url="https://mysecurity.eufylife.com/#/camera",
    )
    monkeypatch.setattr(eufy_cloud, "resolve_profile", lambda name="default": profile)

    monkeypatch.setattr(
        eufy_cloud,
        "_native_fetch_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            eufy_cloud.EufyCloudError("temporary backend timeout")
        ),
    )

    def _unexpected(*args, **kwargs):
        raise AssertionError("webportal fallback should not run")

    monkeypatch.setattr(eufy_cloud, "_webportal_fetch_snapshot", _unexpected)

    with pytest.raises(eufy_cloud.EufyCloudError, match="temporary backend timeout"):
        eufy_cloud.fetch_snapshot("beach", "dev-timeout", timeout=8)


def test_native_media_candidates_extract_nested_urls() -> None:
    device = {
        "params": [{"param_type": 1, "param_value": "https://cdn.example.test/x.jpg"}],
        "metadata": {"stream_url": "rtsp://camera.example.test/live"},
    }

    images, streams = eufy_cloud._native_media_candidates(device, api_base=None)
    assert "https://cdn.example.test/x.jpg" in images
    assert "rtsp://camera.example.test/live" in streams


def test_fetch_snapshot_native_mode_stream_fallback(monkeypatch) -> None:
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
    monkeypatch.setattr(eufy_cloud, "resolve_profile", lambda name="default": profile)

    def _fake_native_session(profile, *, timeout, force_login=False, **_kwargs):
        assert profile.name == "argyle"
        assert timeout == 7
        assert force_login is False
        return "token", "https://api.example.test", b"k" * 32, {}

    def _fake_native_request(profile, endpoint, *, payload=None, timeout=0, retry=True):
        assert profile.name == "argyle"
        assert endpoint == "v2/app/get_devs_list"
        return {
            "code": 0,
            "data": [
                {
                    "device_sn": "dev-stream",
                    "device_name": "Stream Camera",
                    "stream_url": "rtsp://camera.example.test/live",
                }
            ],
        }

    seen: dict[str, object] = {}

    def _fake_stream_frame(stream_url, *, timeout):
        seen["stream_url"] = stream_url
        seen["timeout"] = timeout
        return b"frame-bytes", "image/jpeg"

    monkeypatch.setattr(eufy_cloud, "_native_session", _fake_native_session)
    monkeypatch.setattr(eufy_cloud, "_native_request", _fake_native_request)
    monkeypatch.setattr(eufy_cloud, "_native_fetch_stream_frame", _fake_stream_frame)

    payload, content_type = eufy_cloud.fetch_snapshot("argyle", "dev-stream", timeout=7)
    assert payload == b"frame-bytes"
    assert content_type == "image/jpeg"
    assert seen == {"stream_url": "rtsp://camera.example.test/live", "timeout": 7}


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


def test_auto_solve_native_captcha_success(monkeypatch) -> None:
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
    eufy_cloud._NATIVE_CAPTCHA_OCR_ATTEMPTS.clear()
    eufy_cloud._set_native_captcha("argyle", "cid-ocr", "data:image/png;base64,abc")
    monkeypatch.setattr(
        eufy_cloud,
        "_native_decode_captcha_item",
        lambda _item: b"png-bytes",
    )
    monkeypatch.setattr(
        eufy_cloud,
        "_native_ollama_codes",
        lambda _payload, timeout=0: ["AB12"],
    )
    seen: dict[str, str] = {}

    def _fake_submit(name, captcha_code, timeout=0):
        seen["profile"] = name
        seen["code"] = captcha_code
        eufy_cloud.clear_native_captcha(name)

    monkeypatch.setattr(eufy_cloud, "submit_native_captcha", _fake_submit)

    result = eufy_cloud.auto_solve_native_captcha("argyle", timeout=3, force=True)
    assert result["attempted"] is True
    assert result["solved"] is True
    assert result["code"] == "AB12"
    assert seen == {"profile": "argyle", "code": "AB12"}


def test_auto_solve_native_captcha_skips_repeated_same_challenge(monkeypatch) -> None:
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
    eufy_cloud._NATIVE_CAPTCHA_OCR_ATTEMPTS.clear()
    eufy_cloud._set_native_captcha("argyle", "cid-repeat", "data:image/png;base64,abc")
    monkeypatch.setattr(
        eufy_cloud,
        "_native_decode_captcha_item",
        lambda _item: b"png-bytes",
    )
    calls = {"ocr": 0}

    def _fake_ocr(_payload, timeout=0):
        calls["ocr"] += 1
        return []

    monkeypatch.setattr(eufy_cloud, "_native_ollama_codes", _fake_ocr)

    first = eufy_cloud.auto_solve_native_captcha("argyle")
    second = eufy_cloud.auto_solve_native_captcha("argyle")
    assert first["attempted"] is True
    assert first["solved"] is False
    assert second["attempted"] is False
    assert second["reason"] == "already_attempted_for_challenge"
    assert calls["ocr"] == 1


def test_native_ollama_codes_falls_back_to_tesseract(monkeypatch) -> None:
    monkeypatch.setattr(eufy_cloud.config, "LOCAL_LLM_VISION_MODEL", "")
    monkeypatch.setattr(
        eufy_cloud.shutil,
        "which",
        lambda cmd: "/usr/bin/tesseract" if cmd == "tesseract" else "",
    )

    class _Proc:
        returncode = 0
        stdout = "fVhV\n"
        stderr = ""

    calls: list[list[str]] = []

    def _fake_run(args, **_kwargs):
        calls.append(list(args))
        return _Proc()

    monkeypatch.setattr(eufy_cloud.subprocess, "run", _fake_run)

    codes = eufy_cloud._native_ollama_codes(b"not-a-real-png", timeout=2)
    assert "FVHV" in codes
    assert calls
    assert calls[0][0] == "/usr/bin/tesseract"


def test_fetch_snapshot_native_retries_after_auto_solve(monkeypatch) -> None:
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
    calls = {"fetch": 0}

    def _fake_fetch(_profile, _device_id, *, timeout):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            raise eufy_cloud.EufyCaptchaRequired(
                profile="argyle",
                captcha_id="cid-1",
                captcha_item="data:image/png;base64,abc",
                message="captcha needed",
            )
        return b"jpg", "image/jpeg"

    monkeypatch.setattr(eufy_cloud, "_native_fetch_snapshot", _fake_fetch)
    monkeypatch.setattr(
        eufy_cloud,
        "auto_solve_native_captcha",
        lambda *a, **k: {"attempted": True, "solved": True},
    )

    payload, content_type = eufy_cloud.fetch_snapshot("argyle", "dev-1", timeout=9)
    assert payload == b"jpg"
    assert content_type == "image/jpeg"
    assert calls["fetch"] == 2


def test_list_devices_native_retries_after_auto_solve(monkeypatch) -> None:
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
    calls = {"list": 0}

    def _fake_list(_profile, *, timeout):
        calls["list"] += 1
        if calls["list"] == 1:
            raise eufy_cloud.EufyCaptchaRequired(
                profile="argyle",
                captcha_id="cid-2",
                captcha_item="data:image/png;base64,abc",
                message="captcha needed",
            )
        return [{"device_id": "d1"}]

    monkeypatch.setattr(eufy_cloud, "_native_list_devices", _fake_list)
    monkeypatch.setattr(
        eufy_cloud,
        "auto_solve_native_captcha",
        lambda *a, **k: {"attempted": True, "solved": True},
    )

    devices = eufy_cloud.list_devices("argyle", timeout=9)
    assert devices == [{"device_id": "d1"}]
    assert calls["list"] == 2
