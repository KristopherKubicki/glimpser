from __future__ import annotations

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
