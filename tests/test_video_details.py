import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Dynamically load the module to avoid importing heavy app dependencies
MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "utils" / "video_details.py"
spec = importlib.util.spec_from_file_location("video_details", MODULE_PATH)
video_details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_details)
UTC = timezone.utc


def _make_file(tmp_path, name: str, days_ago: int = 0):
    path = tmp_path / name
    path.write_text("data")
    ts = datetime.utcnow() - timedelta(days=days_ago)
    os.utime(path, (ts.timestamp(), ts.timestamp()))
    return path


def test_get_latest_video_date(tmp_path):
    _make_file(tmp_path, "old.mp4", days_ago=2)
    latest = _make_file(tmp_path, "new.mp4", days_ago=0)
    expected = datetime.fromtimestamp(latest.stat().st_mtime, UTC).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert video_details.get_latest_video_date(str(tmp_path)) == expected


def test_get_latest_screenshot_date(tmp_path):
    _make_file(tmp_path, "shot1.png", days_ago=1)
    latest = _make_file(tmp_path, "shot2.png", days_ago=0)
    expected = datetime.fromtimestamp(latest.stat().st_mtime, UTC).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert video_details.get_latest_screenshot_date(str(tmp_path)) == expected


def test_get_latest_file(tmp_path):
    _make_file(tmp_path, "file1.txt", days_ago=1)
    latest = _make_file(tmp_path, "file2.txt", days_ago=0)
    assert video_details.get_latest_file(str(tmp_path), ext="txt") == latest.name

    link = tmp_path / "latest_camera.txt"
    link.symlink_to(latest.name)
    assert video_details.get_latest_file(str(tmp_path), ext="txt") == str(link)


def test_get_latest_date(tmp_path):
    _make_file(tmp_path, "a.txt", days_ago=2)
    latest = _make_file(tmp_path, "b.txt", days_ago=0)
    expected = datetime.fromtimestamp(latest.stat().st_mtime, UTC).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert video_details.get_latest_date(str(tmp_path), ext="txt") == expected


def test_get_latest_date_empty(tmp_path):
    assert video_details.get_latest_date(str(tmp_path), ext="txt") is None


def test_capture_time_ignores_later_caption_and_sidecar_writes(tmp_path):
    directory = tmp_path / "Camera"
    directory.mkdir()
    older = _make_file(directory, "Camera_20260925180000.png")
    latest = _make_file(directory, "Camera_20260925192212.png", days_ago=1)
    _make_file(directory, "Camera_20260925195959.png.clean.png")
    _make_file(directory, "last_clean.png")
    _make_file(directory, "Camera_20261325195959.png")
    _make_file(directory, "Other_20260925195959.png")
    (directory / "latest_camera.png").symlink_to(older.name)
    assert latest.stat().st_mtime < older.stat().st_mtime
    assert (
        video_details.get_latest_screenshot_date(str(directory))
        == "2026-09-25 19:22:12"
    )


def test_capture_time_resolves_latest_symlink_and_blank_suffix(tmp_path):
    directory = tmp_path / "Camera"
    directory.mkdir()
    image = _make_file(directory, "Camera_20260925192212_blank.png")
    (directory / "latest_camera.png").symlink_to(image.name)
    assert (
        video_details.get_latest_screenshot_date(str(directory))
        == "2026-09-25 19:22:12"
    )


def test_capture_time_missing_directory(tmp_path):
    assert video_details.get_latest_screenshot_date(str(tmp_path / "missing")) is None
