from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import app
from app.utils import weather_brief


def _templates() -> dict[str, dict[str, object]]:
    return {
        "Weather": {
            "groups": "weather",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 11:00:00",
            "last_caption": "Quiet morning with no warning text visible.",
            "url": "https://www.weather.gov/lot/weatherstory",
        },
        "Lightning": {
            "groups": "weather,usa,map",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 10:45:00",
            "last_caption": "Lightning map shows a thunder risk west of town.",
            "url": "https://images.lightningmaps.org/blitzortung/america/",
        },
        "WaukeganBuoy": {
            "groups": "waukegan,harbor,weather,buoy,marine",
            "last_capture_status": "stale_ok",
            "last_screenshot_time": "2026-05-05 09:30:00",
            "last_caption": "Lake camera shows light chop.",
            "url": "https://example.test/buoy.jpg",
        },
        "GeoMagnetic": {
            "groups": "cosmic,geomagnetic,geoelectric,powergrid,spaceweather",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 10:55:00",
            "last_caption": "Geoelectric field is low.",
            "url": "https://example.test/geo.png",
        },
        "Amazon": {
            "groups": "ecom",
            "last_capture_status": "fresh",
            "last_screenshot_time": "2026-05-05 11:00:00",
            "last_caption": "Shopping page.",
            "url": "https://amazon.com",
        },
    }


def test_build_weather_brief_curates_weather_sources():
    brief = weather_brief.build_weather_brief(
        _templates(), now=datetime(2026, 5, 5, 11, 30, 0)
    )

    assert brief["summary"]["total_weather_sources"] == 4
    assert brief["summary"]["fresh_sources"] == 4
    assert brief["summary"]["risk_signals"] >= 1
    assert "Amazon" not in {tile["name"] for tile in brief["top_tiles"]}

    lanes = {section["key"]: section for section in brief["sections"]}
    assert any(tile["name"] == "Lightning" for tile in lanes["now"]["tiles"])
    assert any(tile["name"] == "WaukeganBuoy" for tile in lanes["lake"]["tiles"])
    assert any(
        tile["name"] == "GeoMagnetic" for tile in lanes["infrastructure"]["tiles"]
    )


def test_weather_page_renders_generated_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(weather_brief, "WEATHER_BRIEF_DIR", tmp_path)
    monkeypatch.setattr(
        weather_brief, "WEATHER_BRIEF_JSON", tmp_path / "daily_brief.json"
    )
    monkeypatch.setattr(
        weather_brief, "WEATHER_BRIEF_HTML", tmp_path / "daily_brief.html"
    )

    with (
        patch("app.routes.login_required", lambda view: view),
        patch("app.routes.session", {"user_id": 1}),
        patch("app.routes.template_manager.get_templates", return_value=_templates()),
        patch("app.routes.get_active_groups", return_value=["weather"]),
    ):
        flask_app = app.create_app(
            enable_watchdog=False,
            schedule=False,
            log_cache=False,
        )
        client = flask_app.test_client()
        response = client.get("/weather")

    assert response.status_code == 200
    assert b"Eyebat Local Weather Sheet" in response.data
    assert b"Lightning" in response.data
    assert (tmp_path / "daily_brief.json").exists()
