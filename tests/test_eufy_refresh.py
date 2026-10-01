"""Refresh only verified new frames from the explicitly selected bridge."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.utils import eufy_cloud, scheduling, template_manager
from scripts import eufy_refresh_macmini as refresh


@pytest.mark.parametrize("profile", [None, SimpleNamespace(mode="emulator")])
def test_missing_or_nonexternal_profile_never_contacts_bridge(monkeypatch, profile):
    monkeypatch.setattr(eufy_cloud, "resolve_profile", Mock(return_value=profile))
    client = Mock()
    monkeypatch.setattr(eufy_cloud, "_external_bridge_devices", client)
    with pytest.raises(ValueError):
        refresh.main("example")
    client.assert_not_called()


def test_refresh_uses_configured_profile_and_preserves_other_sources(monkeypatch):
    profile = SimpleNamespace(mode="external")
    monkeypatch.setattr(eufy_cloud, "resolve_profile", Mock(return_value=profile))
    device = {"id": "cam-1", "status": "captured", "snapshot": {"mtime_epoch": 900}}
    client = Mock(return_value=[device])
    monkeypatch.setattr(eufy_cloud, "_external_bridge_devices", client)
    monkeypatch.setattr(refresh.time, "time", lambda: 1000)
    selected = {"url": "eufy://example/cam-1"}
    monkeypatch.setattr(
        template_manager,
        "get_templates",
        lambda: {
            "Selected": selected,
            "Other": {"url": "eufy://other/cam-1"},
            "Web": {"url": "https://example.com"},
            "Missing": {"url": "eufy://example/missing"},
        },
    )
    capture = Mock()
    monkeypatch.setattr(scheduling, "update_camera", capture)
    refresh.main(" Example ")
    client.assert_called_once_with(profile, timeout=8)
    capture.assert_called_once_with("Selected", selected)


@pytest.mark.parametrize(
    "device",
    [
        {},
        {"status": "captured", "snapshot": None},
        {"status": "captured", "snapshot": True},
        {"status": "failed", "snapshot": {"mtime_epoch": 900}},
        {
            "status": "captured",
            "capture_enabled": False,
            "snapshot": {"mtime_epoch": 900},
        },
        {"status": "captured", "snapshot": {"mtime_epoch": 1001}},
        {"status": "captured", "snapshot": {"mtime_epoch": "nan"}},
        {"status": "captured", "snapshot": {"mtime_epoch": -100000}},
    ],
)
def test_unverified_disabled_or_stale_frames_are_preserved(device):
    assert not refresh.needs_refresh(device, {}, 1000)


def test_already_imported_frame_is_not_redated():
    device = {"status": "captured", "snapshot": {"mtime_epoch": 900}}
    assert not refresh.needs_refresh(
        device, {"last_screenshot_time": "1970-01-01T00:15:00Z"}, 1000
    )
