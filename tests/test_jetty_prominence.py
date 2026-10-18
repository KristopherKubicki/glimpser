from datetime import datetime, timedelta

import pytest

from app.blueprints import views
from app.utils.seiche_brief import build_beach_camera_tiles


@pytest.mark.parametrize("profile", ["kitchen", "living", "office", "hal", "public"])
def test_favorite_visibility_preserves_public_boundary(profile):
    fresh = dict(
        groups="beachhouse,beach,eufy",
        last_screenshot_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        capture_failed=0,
        private_camera=1,
        frequency=30,
        url="eufy://macmini/south-jetty",
    )
    templates = {
        "BeachSouthJetty": fresh,
        "BeachNorthJetty": dict(fresh, groups="beachhouse,expected-offline"),
        "UnrelatedPrivate": fresh,
    }
    scenes = views._build_landing_scenes(
        templates,
        views.LANDING_MODE_PROFILES["medium"],
        views.LANDING_CONTENT_PROFILES[profile],
    )
    names = {scene["hero"]["name"] for scene in scenes}
    assert "BeachSouthJetty" not in names
    assert "BeachNorthJetty" not in names
    assert "UnrelatedPrivate" not in names


def test_featured_favorite_does_not_override_freshness_or_maintenance():
    now = datetime.utcnow()
    fresh = dict(
        groups="beachhouse,beach,eufy",
        last_capture_status="fresh",
        last_screenshot_time=now.strftime("%Y-%m-%d %H:%M:%S"),
    )
    templates = {
        "BeachSouthJetty": fresh,
        "BeachShore": fresh,
        "BeachNorthJetty": dict(fresh, groups="beachhouse,expected-offline"),
    }
    tiles = build_beach_camera_tiles(templates, now=now)
    assert tiles[0]["name"] == "BeachSouthJetty"
    assert "BeachNorthJetty" not in {tile["name"] for tile in tiles}
    templates["BeachSouthJetty"] = dict(
        fresh,
        last_screenshot_time=(now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    assert build_beach_camera_tiles(templates, now=now)[0]["name"] == "BeachShore"
