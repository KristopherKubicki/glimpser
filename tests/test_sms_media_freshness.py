import datetime as dt
import os
import time

import pytest
from PIL import Image

from app.utils import sms_media


def make_frame(tmp_path, name, timestamp):
    path = tmp_path / name
    Image.new("RGB", (480, 320), (30, 80, 120)).save(path)
    os.utime(path, (timestamp, timestamp))
    return path


def render(paths, max_age):
    return sms_media._render_sms_gif_from_paths(
        "FrontDoor",
        paths,
        480,
        300000,
        5,
        720,
        max_age,
        source_kind="screenshots",
    )


def record_frames(monkeypatch):
    seen = []
    original = sms_media._render_frame

    def record(path, camera, label, stamp, *args):
        seen.append((path, stamp))
        return original(path, camera, label, stamp, *args)

    monkeypatch.setattr(sms_media, "_render_frame", record)
    return seen


def test_fresh_frame_cannot_admit_old_frames(tmp_path, monkeypatch):
    now = time.time()
    fresh = make_frame(tmp_path, "fresh.png", now - 10)
    old = make_frame(tmp_path, "old.png", now - 86400)
    seen = record_frames(monkeypatch)
    asset = render([fresh, old], 180)
    assert asset.body.startswith(b"GIF")
    assert asset.bytes <= 300000
    assert {path for path, stamp in seen} == {fresh}


def test_all_stale_frames_rejected(tmp_path):
    old = make_frame(tmp_path, "old.png", time.time() - 86400)
    with pytest.raises(sms_media.SmsMediaStale):
        render([old], 180)


def test_each_frame_uses_its_own_capture_timestamp(tmp_path, monkeypatch):
    now = time.time()
    recent = make_frame(tmp_path, "recent.png", now - 70)
    earlier = make_frame(tmp_path, "earlier.png", now - 670)
    seen = record_frames(monkeypatch)
    render([recent, earlier], 900)
    assert {path for path, stamp in seen} == {recent, earlier}
    for path, stamp in seen:
        expected = dt.datetime.fromtimestamp(
            path.stat().st_mtime, dt.timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        assert stamp == expected


def test_future_frame_not_treated_as_fresh(tmp_path):
    future = make_frame(tmp_path, "future.png", time.time() + 3600)
    with pytest.raises(sms_media.SmsMediaStale):
        render([future], 180)
