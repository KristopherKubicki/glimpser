from datetime import datetime, timezone
from unittest.mock import patch

from PIL import Image

from app.utils import timelapse


def test_day_history_stays_bounded_and_plays_for_twenty_seconds(tmp_path):
    now = datetime(2026, 9, 29, 18, tzinfo=timezone.utc).timestamp()
    folder = tmp_path / "DayCamera"
    folder.mkdir()
    for hour in range(25):
        stamp = datetime.fromtimestamp(now - hour * 3600, timezone.utc)
        Image.new("RGB", (40, 30), (hour * 10, 50, 100)).save(
            folder / f"DayCamera_{stamp:%Y%m%d%H%M%S}.png"
        )
    with (
        patch.object(
            timelapse,
            "get_template",
            return_value={"url": "rtsp://camera.test/stream", "frequency": 30},
        ),
        patch.object(timelapse, "source_freshness", return_value={}),
        patch.object(timelapse, "activity_score", return_value=5),
        patch.object(timelapse.config, "SCREENSHOT_DIRECTORY", str(tmp_path)),
        patch.object(timelapse.config, "DATABASE_PATH", str(tmp_path / "test.db")),
    ):
        result = timelapse.build_timelapse("DayCamera", now=now)
    assert result["end"] - result["start"] == 86400
    assert result["frames"] <= 24
    assert 20 <= result["duration"] <= 21
    with Image.open(result["path"]) as image:
        assert image.n_frames == result["frames"]
        assert image.size == (800, 450)


def test_daylight_contributes_but_local_motion_stays_dominant():
    before = Image.new("L", (32, 18), 50)
    assert timelapse.activity_score(before, before) == 0
    brighter = Image.new("L", (32, 18), 70)
    assert timelapse.activity_score(before, brighter) == 5
    local = before.copy()
    for x in range(5):
        for y in range(18):
            local.putpixel((x, y), 100)
    assert timelapse.activity_score(before, local) > 5
    assert timelapse.activity_score(before, Image.new("L", (32, 18), 250)) <= 8


def test_single_exposure_flash_does_not_make_static_history_eligible(tmp_path):
    now = datetime(2026, 9, 29, 18, tzinfo=timezone.utc).timestamp()
    folder = tmp_path / "FlashCamera"
    folder.mkdir()
    for index in range(10):
        stamp = datetime.fromtimestamp(now - index * 600, timezone.utc)
        Image.new("RGB", (40, 30), "white" if index == 4 else "gray").save(
            folder / f"FlashCamera_{stamp:%Y%m%d%H%M%S}.png"
        )
    with (
        patch.object(
            timelapse,
            "get_template",
            return_value={"url": "rtsp://camera.test/stream", "frequency": 10},
        ),
        patch.object(timelapse, "source_freshness", return_value={}),
        patch.object(timelapse.config, "SCREENSHOT_DIRECTORY", str(tmp_path)),
        patch.object(timelapse.config, "DATABASE_PATH", str(tmp_path / "test.db")),
    ):
        assert timelapse.build_timelapse("FlashCamera", now=now) is None


def test_private_timelapse_group_does_not_bypass_safety_filters(monkeypatch):
    monkeypatch.setattr(
        timelapse, "VIEWER_CONFIG", {"timelapse_groups": ["example-site"]}
    )
    template = {"groups": "example-site", "url": "https://example.invalid/image"}
    assert timelapse.eligible(template, "ExampleCamera")
    assert not timelapse.eligible({**template, "groups": "other"}, "ExampleCamera")
    assert not timelapse.eligible(
        {**template, "groups": "example-site,archive"}, "ExampleCamera"
    )
    assert not timelapse.eligible({**template, "capture_failed": True}, "ExampleCamera")
    assert not timelapse.eligible(template, "HubitatExample")
