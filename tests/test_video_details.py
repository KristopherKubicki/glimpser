import importlib.util
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Dynamically load the module to avoid importing heavy app dependencies
MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "utils" / "video_details.py"
spec = importlib.util.spec_from_file_location("video_details", MODULE_PATH)
video_details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_details)


def _make_file(tmp_path, name: str, days_ago: int = 0):
    path = tmp_path / name
    path.write_text("data")
    ts = datetime.utcnow() - timedelta(days=days_ago)
    os.utime(path, (ts.timestamp(), ts.timestamp()))
    return path


def test_get_latest_video_date(tmp_path):
    _make_file(tmp_path, "old.mp4", days_ago=2)
    latest = _make_file(tmp_path, "new.mp4", days_ago=0)
    expected = datetime.utcfromtimestamp(latest.stat().st_mtime).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert video_details.get_latest_video_date(str(tmp_path)) == expected


def test_get_latest_screenshot_date(tmp_path):
    _make_file(tmp_path, "shot1.png", days_ago=1)
    latest = _make_file(tmp_path, "shot2.png", days_ago=0)
    expected = datetime.utcfromtimestamp(latest.stat().st_mtime).strftime(
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
    expected = datetime.utcfromtimestamp(latest.stat().st_mtime).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert video_details.get_latest_date(str(tmp_path), ext="txt") == expected


def test_get_latest_date_empty(tmp_path):
    assert video_details.get_latest_date(str(tmp_path), ext="txt") is None
