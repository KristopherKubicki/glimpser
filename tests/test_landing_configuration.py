"""Private kiosk preferences cannot corrupt generic defaults or host selection."""

import json

import pytest

from app.blueprints import views
from app.landing_config import load_landing_config
from app.landing_defaults import DEFAULTS


def test_unconfigured_presets_have_no_installation_memberships(monkeypatch):
    monkeypatch.delenv("GLIMPSER_LANDING_CONFIG", raising=False)
    config = load_landing_config()
    assert not config["LANDING_HOST_PROFILE_HINTS"]
    assert not config["LANDING_HOST_MODE_HINTS"]
    assert not config["LANDING_PRIORITY_CAMERAS"]
    assert not config["LANDING_PROFILE_EXCLUDED_CAMERAS"]
    for profile in config["LANDING_CONTENT_PROFILES"].values():
        assert not profile.get("camera_minimums")
    config["LANDING_CONTENT_PROFILES"]["public"]["label"] = "Changed"
    assert (
        load_landing_config()["LANDING_CONTENT_PROFILES"]["public"]["label"] == "Public"
    )


def test_valid_private_profile_preserves_generic_fallbacks(tmp_path, monkeypatch):
    profile = DEFAULTS["LANDING_CONTENT_PROFILES"]["office"] | {
        "camera_minimums": ["ExampleDoor"]
    }
    data = {
        "LANDING_CONTENT_PROFILES": {"office": profile},
        "LANDING_PRIORITY_CAMERAS": ["ExampleDoor"],
    }
    path = tmp_path / "landing.json"
    path.write_text(json.dumps(data))
    monkeypatch.setenv("GLIMPSER_LANDING_CONFIG", str(path))
    loaded = load_landing_config()
    assert loaded["LANDING_CONTENT_PROFILES"]["office"] == profile
    assert (
        loaded["LANDING_CONTENT_PROFILES"]["public"]
        == DEFAULTS["LANDING_CONTENT_PROFILES"]["public"]
    )
    monkeypatch.setattr(
        views, "LANDING_PRIORITY_CAMERAS", loaded["LANDING_PRIORITY_CAMERAS"]
    )
    assert views._is_priority_camera("ExampleDoor", {})
    assert not views._is_priority_camera("Other", {})
    assert views._is_priority_camera("Other", {"groups": "priority"})


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"unknown": []},
        {"LANDING_CONTENT_PROFILES": {"office": {"key": "office"}}},
        {"LANDING_PRIORITY_CAMERAS": "private-value"},
        {"LANDING_HOST_PROFILE_HINTS": [["example", "missing"]]},
        {"LANDING_GROUP_BONUSES": {"example": float("nan")}},
        {"LANDING_GROUP_BONUSES": {"example": True}},
    ],
)
def test_invalid_settings_fall_back_atomically(tmp_path, monkeypatch, caplog, data):
    path = tmp_path / "landing.json"
    path.write_text(json.dumps(data))
    monkeypatch.setenv("GLIMPSER_LANDING_CONFIG", str(path))
    assert load_landing_config() == DEFAULTS
    assert "private-value" not in caplog.text and str(path) not in caplog.text


@pytest.mark.parametrize(
    "changes",
    [
        {"scene_size": 0},
        {"rotation_ms": -1},
        {"group_window_sizes": {"example": 0}},
        {"group_rotation_multipliers": {"example": 100}},
        {"all_eligible": "false"},
    ],
)
def test_profile_limits_reject_invalid_scheduling_values(
    tmp_path, monkeypatch, changes
):
    profile = DEFAULTS["LANDING_CONTENT_PROFILES"]["office"] | changes
    path = tmp_path / "landing.json"
    path.write_text(json.dumps({"LANDING_CONTENT_PROFILES": {"office": profile}}))
    monkeypatch.setenv("GLIMPSER_LANDING_CONFIG", str(path))
    assert load_landing_config() == DEFAULTS


def test_host_mappings_require_exact_host_or_first_dns_label(monkeypatch):
    monkeypatch.setattr(
        views, "LANDING_HOST_PROFILE_HINTS", [["example-kiosk", "office"]]
    )
    monkeypatch.setattr(views, "LANDING_HOST_MODE_HINTS", [["example-kiosk", "high"]])
    for host in ("example-kiosk", "EXAMPLE-KIOSK.home.example"):
        assert views._landing_content_profile(None, host)["key"] == "office"
        assert views._landing_mode_profile(None, host)["key"] == "high"
    for host in ("not-example-kiosk", "other.example-kiosk.example"):
        assert views._landing_content_profile(None, host)["key"] == "public"
        assert views._landing_mode_profile(None, host)["key"] == "medium"
    assert views._landing_content_profile("living", "example-kiosk")["key"] == "living"
