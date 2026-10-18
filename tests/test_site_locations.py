"""Census site associations are explicit, private by default, and validated."""

import json

import pytest

from app.site_locations import load_site_locations
from scripts import camera_view_census as census


def seed():
    return {
        "groups": ["example-site"],
        "label": "Example Site",
        "latitude": 0,
        "longitude": 0,
    }


def test_unconfigured_census_does_not_invent_a_site(monkeypatch):
    monkeypatch.delenv("GLIMPSER_SITE_LOCATIONS", raising=False)
    assert load_site_locations() == []
    monkeypatch.setattr(census, "SITE_LOCATION_SEEDS", [])
    metadata = census.build_location_metadata(
        {"groups": "private", "url": "rtsp://192.0.2.1/live"}
    )
    assert metadata["camera"]["latitude"] is None
    assert metadata["camera"]["longitude"] is None
    assert metadata["camera"]["label"] == ""


def test_private_site_matches_only_explicit_selectors(tmp_path, monkeypatch):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps([seed()]))
    monkeypatch.setenv("GLIMPSER_SITE_LOCATIONS", str(path))
    sites = load_site_locations()
    assert sites[0]["private"] is True
    monkeypatch.setattr(census, "SITE_LOCATION_SEEDS", sites)
    assert census.infer_site_location_seed({"groups": "EXAMPLE-SITE"}) == sites[0]
    assert census.infer_site_location_seed({"groups": "other"}) is None
    camera = census.build_location_metadata({"groups": "example-site"})["camera"]
    assert camera["latitude"] == 0 and camera["longitude"] == 0
    assert camera["private"] is True
    explicit = census.build_location_metadata(
        {
            "groups": "example-site",
            "camera_latitude": 1,
            "camera_longitude": 2,
            "camera_location_label": "Recorded",
        }
    )["camera"]
    assert (explicit["latitude"], explicit["longitude"], explicit["label"]) == (
        1,
        2,
        "Recorded",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"latitude": 91},
        {"longitude": float("nan")},
        {"latitude": True},
        {"longitude": None},
        {"private": "false"},
        {"groups": "example-site"},
        {"url_prefixes": ["https://user:private-value@example.invalid/"]},
        {"url_prefixes": ["https://example.invalid/?token=private-value"]},
        {"accuracy": "unsupported"},
    ],
)
def test_invalid_seed_disables_inference_without_logging_private_data(
    tmp_path, monkeypatch, caplog, changes
):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps([seed() | changes]))
    monkeypatch.setenv("GLIMPSER_SITE_LOCATIONS", str(path))
    assert load_site_locations() == []
    assert "private-value" not in caplog.text and str(path) not in caplog.text
