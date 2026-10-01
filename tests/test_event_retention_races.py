"""Event retention tolerates concurrent cleanup and respects explicit zero."""

import os
from pathlib import Path

import pytest

from app.utils import event_buffer as eb


def test_numeric_zero_pre_event_window_is_respected():
    assert eb._template_ints({"event_buffer_pre_seconds": 0})["pre_seconds"] == 0
    assert eb._template_ints({"event_buffer_pre_seconds": "0"})["pre_seconds"] == 0


@pytest.mark.parametrize("value", [None, "", "invalid"])
def test_missing_or_invalid_pre_event_window_keeps_default(value):
    assert eb._template_ints({"event_buffer_pre_seconds": value})["pre_seconds"] == 8


def test_retention_survives_file_removed_after_listing(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "EVENT_BUFFER_ROOT", tmp_path)
    directory = tmp_path / "camera" / "events"
    directory.mkdir(parents=True)
    vanished = directory / "vanished.gif"
    expired = directory / "expired.gif"
    current = directory / "current.gif"
    for path, stamp in [(vanished, 10), (expired, 10), (current, 100000)]:
        path.write_bytes(b"gif")
        os.utime(path, (stamp, stamp))
    original_stat = Path.stat

    def stat(path, *args, **kwargs):
        if path == vanished:
            path.unlink(missing_ok=True)
            raise FileNotFoundError(str(path))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    eb._prune_events("camera", now=100001)
    assert not expired.exists()
    assert current.exists()


def test_retention_applies_age_then_count_in_one_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "EVENT_BUFFER_ROOT", tmp_path)
    monkeypatch.setattr(eb, "_MAX_EVENT_FILES", 2)
    monkeypatch.setattr(eb, "_EVENT_RETENTION_SECONDS", 100)
    directory = tmp_path / "camera" / "events"
    directory.mkdir(parents=True)
    for name, stamp in [("expired", 1), ("old", 91), ("middle", 92), ("new", 93)]:
        path = directory / f"{name}.gif"
        path.write_bytes(b"gif")
        os.utime(path, (stamp, stamp))
    temporary = directory / "inflight.gif.tmp"
    temporary.write_bytes(b"partial")
    eb._prune_events("camera", now=101)
    assert sorted(p.name for p in directory.glob("*.gif")) == ["middle.gif", "new.gif"]
    assert temporary.exists()
