import pytest

from app.blueprints import views


@pytest.mark.parametrize("profile", ["living", "office", "hal"])
def test_all_healthy_feeds_are_retained(profile):
    content = dict(views.LANDING_CONTENT_PROFILES[profile], all_eligible=True)
    assert content["all_eligible"]
    scenes = [
        {
            "id": str(i),
            "group_name": "systems",
            "hero": {
                "name": str(i),
                "lanes": ("ops",),
                "last_screenshot_time": "2026-10-01 00:00:00",
            },
            "hero_score": i,
            "profile_score": i,
            "scene_score": i,
            "event_score": 0,
        }
        for i in range(240)
    ]
    result = views._compose_profiled_scenes(scenes, content, 80)
    assert len(result) == 240
    assert len({s["hero"]["name"] for s in result}) == 240


@pytest.mark.parametrize("profile", ["living", "office", "hal"])
def test_broad_pool_still_excludes_unusable_and_private_feeds(profile):
    from datetime import datetime

    fresh = dict(
        groups="systems",
        last_screenshot_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        capture_failed=0,
        private_camera=0,
        url="https://example.test/image.jpg",
    )
    templates = {
        "Healthy": fresh,
        "HouseSystemsMap": dict(fresh, groups="systems,private"),
        "Secret": dict(fresh, private_camera=1),
        "Archived": dict(fresh, groups="archive"),
        "Failed": dict(fresh, capture_failed=1),
        "Old": dict(fresh, last_screenshot_time="2000-01-01 00:00:00"),
        "ErrorPage": dict(fresh, last_caption="Access denied"),
    }
    scenes = views._build_landing_scenes(
        templates,
        views.LANDING_MODE_PROFILES["medium"],
        dict(views.LANDING_CONTENT_PROFILES[profile], all_eligible=True),
    )
    names = {s["hero"]["name"] for s in scenes}
    assert names.intersection(templates) == {"Healthy"}
    public = views._build_landing_scenes(
        templates,
        views.LANDING_MODE_PROFILES["medium"],
        views.LANDING_CONTENT_PROFILES["public"],
    )
    assert "HouseSystemsMap" not in {s["hero"]["name"] for s in public}
