from datetime import datetime, timedelta

import pytest

from app.blueprints import views
from app.blueprints.views import _office_scene_dwell_ms

NOW = datetime(2026, 9, 26, 0, 0)


def scene(name="FrontDoor", lanes=("home",), **extra):
    return {
        "group_name": "highlights",
        "hero": {
            "name": name,
            "lanes": lanes,
            "last_screenshot_time": (NOW - timedelta(minutes=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "freshness": {},
            **extra,
        },
    }


@pytest.mark.parametrize(
    "name,lanes,expected",
    [
        ("FrontDoor", ("home",), 35000),
        ("ExampleShop", ("retail",), 35000),
        ("HubitatPower", ("ops",), 40000),
        ("ExampleStatus", ("ops",), 40000),
        ("SheboyganBeach", ("scenic",), 35000),
        ("BandwidthTX", ("ops",), 0),
        ("RandomTraffic", ("scenic",), 0),
    ],
)
def test_selective_office_dwell(name, lanes, expected, monkeypatch):
    monkeypatch.setattr(
        views,
        "LANDING_CONFIG",
        views.LANDING_CONFIG | {"LANDING_STATUS_CAMERAS": ["ExampleStatus"]},
    )
    assert _office_scene_dwell_ms(scene(name, lanes), NOW) == expected


@pytest.mark.parametrize(
    "flag",
    [
        "capture_overdue",
        "retained",
        "source_unchanged",
        "older",
        "waiting_for_browser",
        "clock_ahead",
        "low_light",
    ],
)
def test_degraded_capture_does_not_get_long_hold(flag):
    assert _office_scene_dwell_ms(scene(freshness={flag: True}), NOW) == 0


def test_recent_motion_outweighs_recent_video():
    s = scene(
        last_motion_time=(NOW - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S"),
        last_video_time=(NOW - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    assert _office_scene_dwell_ms(s, NOW) == 50000
    s["hero"]["last_motion_time"] = (NOW - timedelta(minutes=6)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert _office_scene_dwell_ms(s, NOW) == 45000
    s["hero"]["last_video_time"] = (NOW - timedelta(minutes=16)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert _office_scene_dwell_ms(s, NOW) == 35000


@pytest.mark.parametrize(
    "capture",
    [
        None,
        "bad-date",
        (NOW - timedelta(minutes=31)).strftime("%Y-%m-%d %H:%M:%S"),
        (NOW + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
    ],
)
def test_old_unknown_or_future_capture_does_not_get_long_hold(capture):
    assert _office_scene_dwell_ms(scene(last_screenshot_time=capture), NOW) == 0
