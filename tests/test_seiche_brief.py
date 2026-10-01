from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import app
from app.utils import seiche_brief


def _water_payload(station_id: str, name: str, values: list[float]) -> dict:
    start_hour = 0
    return {
        "metadata": {"id": station_id, "name": name},
        "data": [
            {
                "t": f"2026-05-05 {start_hour + index:02d}:00",
                "v": f"{value:.3f}",
                "s": "0.001",
                "f": "0,0,0,0",
                "q": "p",
            }
            for index, value in enumerate(values)
        ],
    }


def _wind_payload() -> dict:
    return {
        "metadata": {"id": "9087044", "name": "Calumet Harbor"},
        "data": [
            {
                "t": "2026-05-05 10:00",
                "s": "14.0",
                "d": "10.0",
                "dr": "N",
                "g": "21.5",
                "f": "0,0",
            },
            {
                "t": "2026-05-05 11:00",
                "s": "16.0",
                "d": "15.0",
                "dr": "NNE",
                "g": "23.0",
                "f": "0,0",
            },
        ],
    }


def _payloads() -> tuple[dict, dict]:
    water = {
        "9087044": _water_payload(
            "9087044",
            "Calumet Harbor",
            [1.00, 1.08, 1.12, 1.22, 1.34, 1.48, 1.55, 1.62, 1.70, 1.82, 1.90, 2.02],
        ),
        "9087057": _water_payload(
            "9087057",
            "Milwaukee",
            [1.50, 1.48, 1.46, 1.45, 1.43, 1.42, 1.42, 1.43, 1.44, 1.45, 1.46, 1.47],
        ),
        "9087023": _water_payload(
            "9087023",
            "Ludington",
            [1.60, 1.59, 1.58, 1.57, 1.56, 1.56, 1.55, 1.55, 1.54, 1.54, 1.53, 1.53],
        ),
    }
    wind = {"9087044": _wind_payload()}
    return water, wind


def _beach_templates() -> dict[str, dict[str, object]]:
    return {
        "BeachShore": {
            "groups": "beachhouse,beach,home,regional,eufy",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 11:25:00",
            "last_caption": "Beach house shore camera looking across the lake.",
        },
        "BeachNorthJetty": {
            "groups": "beachhouse,beach,home,regional,eufy",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 11:20:00",
            "last_caption": "North jetty shows waves and shoreline.",
        },
        "Warehouse": {
            "groups": "industrial",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 11:20:00",
        },
    }


def test_build_seiche_brief_derives_water_level_signals():
    water, wind = _payloads()
    brief = seiche_brief.build_seiche_brief(
        water,
        wind,
        now=datetime(2026, 5, 5, 11, 30, 0),
    )

    assert brief["summary"]["fresh_water_level_sources"] == 3
    assert brief["summary"]["primary_site"] == "Pleasant Prairie"
    assert brief["pleasant_prairie"]["name"] == "Pleasant Prairie"
    assert 1.6 < brief["summary"]["primary_level_ft_lwd"] < 1.8
    assert brief["summary"]["primary_trend"] == "rising"
    assert brief["summary"]["calumet_trend"] == "rising"
    assert brief["lake_tilt"]["south_vs_milwaukee_in"] > 6
    assert brief["wind"]["setup_hint"] == "wind favors south-shore setup"
    assert brief["summary"]["signal_score"] > 40
    assert brief["stations"][0]["position_24h_pct"] == 100
    assert brief["wind"]["south_push_pct"] > 50
    assert brief["celestial"]["phase"]
    assert brief["celestial"]["phase_angle"] >= 0
    assert any(item["title"] == "Lake tilt" for item in brief["watch_items"])


def test_build_beach_camera_tiles_prioritizes_beach_house():
    tiles = seiche_brief.build_beach_camera_tiles(
        _beach_templates(),
        now=datetime(2026, 5, 5, 11, 30, 0),
    )

    assert [tile["name"] for tile in tiles[:2]] == ["BeachShore", "BeachNorthJetty"]
    assert "Warehouse" not in {tile["name"] for tile in tiles}
    assert tiles[0]["image_url"] == "/last_screenshot/BeachShore"
    assert tiles[0]["freshness_pct"] == 100
    assert tiles[0]["freshness_state"] == "fresh"


def test_seiche_page_renders_generated_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(seiche_brief, "SEICHE_BRIEF_DIR", tmp_path)
    monkeypatch.setattr(
        seiche_brief, "SEICHE_BRIEF_JSON", tmp_path / "daily_seiche.json"
    )
    monkeypatch.setattr(
        seiche_brief, "SEICHE_BRIEF_HTML", tmp_path / "daily_seiche.html"
    )
    water, wind = _payloads()
    brief = seiche_brief.build_seiche_brief(
        water,
        wind,
        now=datetime(2026, 5, 5, 11, 30, 0),
    )
    seiche_brief.write_seiche_brief(brief)

    with (
        patch("app.routes.login_required", lambda view: view),
        patch("app.routes.session", {"user_id": 1}),
        patch("app.routes.get_active_groups", return_value=["weather"]),
        patch(
            "app.routes.template_manager.get_templates", return_value=_beach_templates()
        ),
        patch("app.blueprints.views.load_or_generate_seiche_brief", return_value=brief),
    ):
        flask_app = app.create_app(
            enable_watchdog=False,
            schedule=False,
            log_cache=False,
        )
        client = flask_app.test_client()
        response = client.get("/seiche")

    assert response.status_code == 200
    assert b"Seiche Clock" in response.data
    assert b"Pleasant Prairie" in response.data
    assert b"Calumet Harbor" in response.data
    assert b"Lake Michigan" in response.data
    assert b"BeachShore" in response.data
