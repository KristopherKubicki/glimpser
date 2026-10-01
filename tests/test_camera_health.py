import datetime as dt
import os

from PIL import Image

from app.utils.camera_health import (
    assess_camera_health,
    build_camera_health_report,
    format_camera_health_report,
)

NOW = dt.datetime(2026, 5, 2, 22, 0, tzinfo=dt.timezone.utc)


def _png(path):
    Image.new("RGB", (8, 8), (20, 40, 60)).save(path)


def test_assess_camera_health_reports_healthy_camera(tmp_path):
    screenshot_dir = tmp_path / "screenshots"
    video_dir = tmp_path / "video"
    camera_dir = screenshot_dir / "Cam1"
    camera_dir.mkdir(parents=True)
    video_dir.mkdir()
    frame = camera_dir / "Cam1_20260502215500.png"
    _png(frame)
    os.symlink(frame, camera_dir / "latest_camera.png")

    row = assess_camera_health(
        "Cam1",
        {
            "url": "https://example.com/cam.jpg",
            "frequency": 15,
            "last_screenshot_time": "2026-05-02 21:55:00",
            "capture_failed": 0,
        },
        screenshot_dir,
        video_dir,
        now=NOW,
    )

    assert row["status"] == "healthy"
    assert row["issues"] == []
    assert row["latest_camera_state"] == "ok"


def test_assess_camera_health_flags_broken_and_stale_camera(tmp_path):
    screenshot_dir = tmp_path / "screenshots"
    video_dir = tmp_path / "video"
    camera_dir = screenshot_dir / "Cam1"
    camera_dir.mkdir(parents=True)
    video_dir.mkdir()
    os.symlink(camera_dir / "missing.png", camera_dir / "latest_camera.png")

    row = assess_camera_health(
        "Cam1",
        {
            "url": "rtsp://192.168.1.230/live",
            "frequency": 15,
            "last_screenshot_time": "2026-05-02 18:00:00",
            "capture_failed": 1,
        },
        screenshot_dir,
        video_dir,
        now=NOW,
    )

    assert row["status"] == "failing"
    assert "capture_failing" in row["buckets"]
    assert "broken_latest" in row["buckets"]
    assert "no_frames" in row["buckets"]
    assert "private_route_risk" in row["buckets"]


def test_build_and_format_camera_health_report_summarizes_issues(tmp_path):
    screenshot_dir = tmp_path / "screenshots"
    video_dir = tmp_path / "video"
    camera_dir = screenshot_dir / "Good"
    camera_dir.mkdir(parents=True)
    video_dir.mkdir()
    frame = camera_dir / "Good_20260502215500.png"
    _png(frame)
    os.symlink(frame, camera_dir / "latest_camera.png")

    report = build_camera_health_report(
        {
            "Good": {
                "url": "https://example.com/good.jpg",
                "frequency": 15,
                "last_screenshot_time": "2026-05-02 21:55:00",
            },
            "Missing": {
                "url": "https://example.com/missing.jpg",
                "frequency": 15,
                "last_screenshot_time": "",
                "capture_failed": 1,
            },
        },
        screenshot_dir,
        video_dir,
        now=NOW,
    )

    text = format_camera_health_report(report)

    assert report["summary"]["total"] == 2
    assert report["summary"]["healthy"] == 1
    assert report["summary"]["failing"] == 1
    assert "Missing [failing]" in text
    assert "Good [healthy]" not in text


def test_archived_source_stale_templates_do_not_pollute_default_report(tmp_path):
    screenshot_dir = tmp_path / "screenshots"
    video_dir = tmp_path / "video"
    camera_dir = screenshot_dir / "OldSource"
    camera_dir.mkdir(parents=True)
    video_dir.mkdir()

    report = build_camera_health_report(
        {
            "OldSource": {
                "url": "https://example.com/dead.jpg",
                "frequency": 15,
                "groups": "archive,source-stale",
                "last_screenshot_time": "",
                "capture_failed": 1,
            },
        },
        screenshot_dir,
        video_dir,
        now=NOW,
    )

    default_text = format_camera_health_report(report)
    archived_text = format_camera_health_report(report, include_archived=True)

    assert report["summary"]["archived"] == 1
    assert report["summary"]["archived_template"] == 1
    assert "capture_failing" not in report["summary"]
    assert "OldSource [archived]" not in default_text
    assert "OldSource [archived]" in archived_text
