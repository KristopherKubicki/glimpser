"""Private dashboard membership and safe generic inventory filtering."""

import json

import pytest

from app import viewer_policy as viewer
from app.viewer_config import load_viewer_config


def test_unconfigured_viewer_uses_generic_defaults(monkeypatch):
    monkeypatch.delenv("GLIMPSER_VIEWER_CONFIG", raising=False)
    assert load_viewer_config() == {}
    monkeypatch.setattr(viewer, "VIEWER_CONFIG", {})
    assert viewer.dashboard_matches("security", "Example", {"groups": "security"})
    assert not viewer.dashboard_matches("security", "Example", {"groups": "other"})


def test_private_memberships_and_review_reasons_load(tmp_path, monkeypatch):
    path = tmp_path / "viewer.json"
    path.write_text(
        json.dumps(
            {
                "context_views": {"arrivals": {"Entrance": ["ExampleDoor"]}},
                "rotation_review_holds": {"ExampleBroken": "Offline placeholder"},
                "private_groups": ["PrivateSite"],
                "status_groups": ["ExampleSite", "POWER"],
                "navigation_groups": ["ExampleSite"],
                "google_live_cameras": ["ExampleDoor"],
            }
        )
    )
    monkeypatch.setenv("GLIMPSER_VIEWER_CONFIG", str(path))
    data = load_viewer_config()
    assert data["private_groups"] == ["privatesite"]
    assert data["status_groups"] == ["examplesite", "power"]
    assert data["navigation_groups"] == ["examplesite"]
    assert data["google_live_cameras"] == ["ExampleDoor"]
    assert data["rotation_review_holds"]["ExampleBroken"] == "Offline placeholder"
    monkeypatch.setattr(viewer, "CONTEXT_VIEWS", data["context_views"])
    assert viewer.dashboard_matches("arrivals", "ExampleDoor", {})
    assert not viewer.dashboard_matches("arrivals", "Other", {})
    assert not viewer.dashboard_matches(
        "arrivals", "ExampleDoor", {"groups": "archive"}
    )


@pytest.mark.parametrize(
    "settings",
    [
        None,
        {"security_cameras": "private-name"},
        {"status_groups": "private-name"},
        {"context_views": {"unknown": {}}},
        {"rotation_review_holds": []},
    ],
)
def test_invalid_configuration_does_not_log_private_values(
    tmp_path, monkeypatch, caplog, settings
):
    path = tmp_path / "viewer.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setenv("GLIMPSER_VIEWER_CONFIG", str(path))
    assert load_viewer_config() == {}
    assert "private-name" not in caplog.text and str(path) not in caplog.text


@pytest.mark.parametrize(
    "dashboard,name,groups",
    [
        ("security", "ExampleDoor", "archive"),
        ("systems", "ExampleHub", "systems,archive"),
    ],
)
def test_archived_configured_cameras_stay_out_of_dashboards(
    monkeypatch, dashboard, name, groups
):
    monkeypatch.setattr(
        viewer,
        "VIEWER_CONFIG",
        {"security_cameras": ["ExampleDoor"], "systems_cameras": ["ExampleHub"]},
    )
    assert not viewer.dashboard_matches(dashboard, name, {"groups": groups})


@pytest.mark.parametrize(
    "template",
    [
        {"groups": "regional,private"},
        {"groups": "regional,archive"},
        {"groups": "regional,privatesite"},
        {"groups": "regional", "private_camera": True},
    ],
)
def test_regional_never_includes_private_or_archived_feeds(monkeypatch, template):
    monkeypatch.setattr(viewer, "VIEWER_CONFIG", {"private_groups": ["privatesite"]})
    assert not viewer.dashboard_matches("regional", "Example", template)


def test_configured_hold_excludes_regional_feed(monkeypatch):
    monkeypatch.setattr(viewer, "VIEWER_CONFIG", {})
    monkeypatch.setattr(
        viewer, "QUARANTINED_PRESENTATION", frozenset({"ExampleBroken"})
    )
    assert not viewer.dashboard_matches(
        "regional", "ExampleBroken", {"groups": "regional"}
    )
    assert viewer.dashboard_matches(
        "regional", "ExampleHealthy", {"groups": "regional"}
    )


@pytest.mark.parametrize(
    "options",
    [
        {"provider": "unknown"},
        {"profile": "invalid"},
        {"quality": "invalid"},
        {"source_fps": True},
        {"source_fps": float("nan")},
        {"source_fps": -1},
        {"source_fps": 121},
        {"provider": []},
        None,
    ],
)
def test_invalid_kiosk_options_fail_closed(tmp_path, monkeypatch, options):
    path = tmp_path / "viewer.json"
    path.write_text(json.dumps({"kiosk_live": {"ExampleDoor": options}}))
    monkeypatch.setenv("GLIMPSER_VIEWER_CONFIG", str(path))
    assert load_viewer_config() == {}


def test_kiosk_settings_only_expose_display_and_stream_options(tmp_path, monkeypatch):
    path = tmp_path / "viewer.json"
    path.write_text(
        json.dumps(
            {
                "kiosk_live": {
                    "ExampleDoor": {
                        "provider": "stream",
                        "profile": "main",
                        "quality": "auto",
                        "label": "Example entrance",
                        "source_fps": 1,
                        "url": "rtsp://example.invalid/private",
                        "unrecognized": "private",
                    }
                }
            }
        )
    )
    monkeypatch.setenv("GLIMPSER_VIEWER_CONFIG", str(path))
    assert load_viewer_config()["kiosk_live"]["ExampleDoor"] == {
        "provider": "stream",
        "profile": "main",
        "quality": "auto",
        "label": "Example entrance",
        "source_fps": 1,
    }


@pytest.mark.parametrize(
    "settings",
    [
        {"priority_handoffs": {"ExampleDoor": "ExampleApproach"}},
        {"priority_handoffs": []},
        {"preferred_areas": {"arrivals": []}},
        {"dashboard_group_order": "weather"},
        {"security_approaches": [None]},
    ],
)
def test_invalid_dashboard_rules_fail_closed(tmp_path, monkeypatch, settings):
    path = tmp_path / "viewer.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setenv("GLIMPSER_VIEWER_CONFIG", str(path))
    assert load_viewer_config() == {}


def test_private_dashboard_rules_load(tmp_path, monkeypatch):
    path = tmp_path / "viewer.json"
    path.write_text(
        json.dumps(
            {
                "priority_handoffs": {"ExampleDoor": ["ExampleApproach"]},
                "preferred_areas": {"arrivals": "Entrance"},
                "dashboard_group_order": ["Weather"],
                "security_approaches": ["ExampleDoor"],
            }
        )
    )
    monkeypatch.setenv("GLIMPSER_VIEWER_CONFIG", str(path))
    config = load_viewer_config()
    assert config["priority_handoffs"] == {"ExampleDoor": ["ExampleApproach"]}
    assert config["dashboard_group_order"] == ["weather"]
    assert config["security_approaches"] == ["ExampleDoor"]
    assert config["preferred_areas"] == {"arrivals": "Entrance"}


def test_dashboard_grouping_and_preferred_area_respect_filtered_inventory(monkeypatch):
    from app.utils import visual_dashboard as dashboard

    monkeypatch.setattr(
        dashboard,
        "VIEWER_CONFIG",
        {
            "dashboard_group_order": ["weather", "plants"],
            "preferred_areas": {"regional": "Weather", "security": "Approaches"},
            "security_approaches": ["ExampleDoor"],
        },
    )
    monkeypatch.setattr(
        dashboard,
        "source_freshness",
        lambda *args: {
            "older": False,
            "retained": False,
            "unchanged_since": "",
            "clock_ahead": False,
        },
    )
    monkeypatch.setattr(dashboard, "landing_feed_issue", lambda details: "")
    templates = {
        "ExampleWeather": {"groups": "weather,plants"},
        "ExampleArchived": {"groups": "weather,archive"},
        "ExamplePrivate": {"groups": "weather,private"},
    }
    model = dashboard.build_visual_dashboard(templates, "regional")
    assert [c["name"] for c in model["cameras"]] == ["ExampleWeather"]
    assert model["cameras"][0]["group"] == "Weather"
    assert model["preferred_area"] == "Weather"
    assert dashboard.build_visual_dashboard({}, "regional")["preferred_area"] == ""
    model = dashboard.build_visual_dashboard(
        {"ExampleDoor": {"groups": "security"}}, "security"
    )
    assert model["cameras"][0]["group"] == "Approaches"
    assert model["preferred_area"] == "Approaches"
