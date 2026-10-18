"""Host exceptions must be explicit, exact and safe to leave unconfigured."""

import json
from unittest.mock import Mock

import pytest

from app import capture_policy as policy
from app.utils import screenshots


def test_absent_configuration_has_no_exceptions(monkeypatch):
    monkeypatch.delenv("GLIMPSER_CAPTURE_POLICY", raising=False)
    assert policy.load_capture_policy() == {}


@pytest.mark.parametrize(
    "settings",
    [
        {"hubitat_hosts": "hub.example"},
        {"hubitat_hosts": ["user:secret@hub.example"]},
        {"admin_excluded_hosts": ["https://host.example"]},
        {
            "variable_size_images": [
                {"host": "desktop.example", "path": "/image?token=secret"}
            ]
        },
        {
            "variable_size_images": [
                {"host": "desktop.example", "path": "//other.example/image"}
            ]
        },
        None,
    ],
)
def test_invalid_policy_fails_closed_without_disclosing_contents(
    tmp_path, monkeypatch, caplog, settings
):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setenv("GLIMPSER_CAPTURE_POLICY", str(path))
    assert policy.load_capture_policy() == {}
    assert "secret" not in caplog.text
    assert str(path) not in caplog.text


def test_valid_policy_and_exact_image_scope(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "hubitat_hosts": ["HUB.EXAMPLE"],
                "slow_rtsp_cameras": ["ExampleEncoder"],
                "variable_size_images": [
                    {"host": "desktop.example", "path": "/Desktop.png"}
                ],
            }
        )
    )
    monkeypatch.setenv("GLIMPSER_CAPTURE_POLICY", str(path))
    loaded = policy.load_capture_policy()
    assert loaded["hubitat_hosts"] == ["hub.example"]
    assert loaded["slow_rtsp_cameras"] == ["ExampleEncoder"]
    monkeypatch.setattr(policy, "CAPTURE_POLICY", loaded)
    assert policy.variable_size_image("https://desktop.example:9000/Desktop.png?v=2")
    for url in (
        "https://desktop.example.evil/Desktop.png",
        "https://desktop.example/desktop.png",
        "https://other.example/Desktop.png",
        "ftp://desktop.example/Desktop.png",
    ):
        assert not policy.variable_size_image(url)


def test_hubitat_requires_configured_host_or_exact_cloud_host(monkeypatch):
    monkeypatch.setattr(policy, "CAPTURE_POLICY", {"hubitat_hosts": ["hub.example"]})
    detect = screenshots._is_hubitat_cloud_dashboard_url
    assert detect("https://hub.example/dashboard/ui/1")
    assert not detect("https://other.example/dashboard/ui/1")
    assert detect("https://cloud.hubitat.com/apps/1/ui")
    assert not detect("https://cloud.hubitat.com.evil/apps/1/ui")
    assert not detect("https://other.example/apps/1/ui?target=cloud.hubitat.com")


def test_admin_exclusion_is_exact_and_opt_in(monkeypatch):
    monkeypatch.setattr(screenshots, "_is_lan_target", Mock(return_value=True))
    monkeypatch.setattr(policy, "CAPTURE_POLICY", {})
    url = "http://service.example/admin"
    assert screenshots._browser_capture_profile(url)["allow_private_network_images"]
    monkeypatch.setattr(
        policy, "CAPTURE_POLICY", {"admin_excluded_hosts": ["service.example"]}
    )
    assert not screenshots._browser_capture_profile(url).get(
        "allow_private_network_images", False
    )
    assert screenshots._browser_capture_profile("http://other.example/admin")[
        "allow_private_network_images"
    ]


@pytest.mark.parametrize(
    "settings",
    [
        {"caption_detail_cameras": "ExampleCamera"},
        {"caption_detail_prefixes": [""]},
        {"dashboard_camera_labels": {"ExampleCamera": []}},
        {"dashboard_camera_labels": []},
    ],
)
def test_invalid_caption_and_label_settings_fail_closed(
    tmp_path, monkeypatch, settings
):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setenv("GLIMPSER_CAPTURE_POLICY", str(path))
    assert policy.load_capture_policy() == {}


def test_configured_caption_sizes_preserve_device_detail(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "caption_detail_cameras": ["ExampleDoor"],
                "caption_detail_prefixes": ["ExampleSite_"],
                "dashboard_camera_labels": {"ExampleDoor": "Example entrance"},
            }
        )
    )
    monkeypatch.setenv("GLIMPSER_CAPTURE_POLICY", str(path))
    monkeypatch.setattr(policy, "CAPTURE_POLICY", policy.load_capture_policy())
    assert policy.caption_image_size("HubitatExample") == 1536
    assert policy.caption_image_size("ExampleDoor") == 1024
    assert policy.caption_image_size("ExampleSite_Entrance") == 1024
    assert policy.caption_image_size("ExampleDoorOther") == 512
    assert policy.caption_image_size("examplesite_Entrance") == 512
    assert policy.caption_image_size(None) == 512
    assert policy.CAPTURE_POLICY["dashboard_camera_labels"] == {
        "ExampleDoor": "Example entrance"
    }
