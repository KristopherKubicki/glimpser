"""Location defaults require explicit, valid installation configuration."""

import json

import pytest

from app.location_config import load_location_config


def site():
    return {
        "groups": ["Example"],
        "url_prefixes": ["rtsp://camera.example.test/"],
        "label": "Example site",
        "latitude": 40,
        "longitude": -80,
        "evidence": "Operator supplied test fixture",
    }


def test_missing_configuration_supplies_no_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("GLIMPSER_LOCATION_CONFIG", str(tmp_path / "absent.json"))
    assert load_location_config() == []


def test_explicit_location_is_private_by_default(tmp_path, monkeypatch):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps({"sites": [site()]}))
    monkeypatch.setenv("GLIMPSER_LOCATION_CONFIG", str(path))
    result = load_location_config()
    assert result[0]["private"] is True
    assert result[0]["groups"] == ["example"]
    assert result[0]["latitude"] == 40


@pytest.mark.parametrize(
    "changes",
    [
        {"latitude": 91},
        {"latitude": True},
        {"longitude": None},
        {"latitude": float("nan")},
        {"private": "false"},
        {"groups": [], "url_prefixes": []},
        {"url_prefixes": ["javascript:alert(1)"]},
        {"url_prefixes": ["https://operator@camera.example.test/"]},
    ],
)
def test_invalid_site_disables_entire_inventory(tmp_path, monkeypatch, changes):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps({"sites": [site(), site() | changes]}))
    monkeypatch.setenv("GLIMPSER_LOCATION_CONFIG", str(path))
    assert load_location_config() == []
