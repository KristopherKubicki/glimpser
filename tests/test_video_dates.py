import datetime
import types

from app.utils import video_archiver


def test_get_video_creation_time_success(monkeypatch):
    fake_result = types.SimpleNamespace(stdout="2024-01-01T12:00:00Z", stderr="")
    monkeypatch.setattr(video_archiver.subprocess, "run", lambda *a, **k: fake_result)
    ts = video_archiver.get_video_creation_time("dummy.mp4")
    assert ts == datetime.datetime(2024, 1, 1, 12, 0, 0)


def test_get_video_creation_time_error(monkeypatch):
    def fail(*a, **k):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(video_archiver.subprocess, "run", fail)
    assert video_archiver.get_video_creation_time("dummy.mp4") is None


def test_is_video_expired_old_file(monkeypatch):
    now = datetime.datetime.utcnow().timestamp()
    old_ts = now - 10 * 86400
    monkeypatch.setattr(video_archiver.os.path, "exists", lambda p: True)
    monkeypatch.setattr(video_archiver.os.path, "getctime", lambda p: old_ts)
    monkeypatch.setattr(video_archiver, "get_video_creation_time", lambda p: None)
    assert video_archiver.is_video_expired("file.mp4", 5)


def test_is_video_expired_recent_file(monkeypatch):
    now = datetime.datetime.utcnow().timestamp()
    new_ts = now - 2 * 86400
    monkeypatch.setattr(video_archiver.os.path, "exists", lambda p: True)
    monkeypatch.setattr(video_archiver.os.path, "getctime", lambda p: new_ts)
    monkeypatch.setattr(video_archiver, "get_video_creation_time", lambda p: None)
    assert not video_archiver.is_video_expired("file.mp4", 5)


def test_is_video_expired_missing_file(monkeypatch):
    monkeypatch.setattr(video_archiver.os.path, "exists", lambda p: False)
    assert not video_archiver.is_video_expired("missing.mp4", 5)
