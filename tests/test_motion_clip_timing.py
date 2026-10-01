"""Motion clips keep acquisition timing and both ends of their event window."""

from pathlib import Path

import pytest
from PIL import Image

from app.utils import event_buffer as eb


@pytest.fixture
def buffer(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "EVENT_BUFFER_ROOT", tmp_path)
    monkeypatch.setattr(
        eb,
        "get_template",
        lambda name: {
            "event_buffer_enabled": True,
            "event_buffer_fps": 2,
            "event_buffer_seconds": 60,
            "event_buffer_pre_seconds": 10,
            "event_buffer_post_seconds": 6,
        },
    )
    directory = tmp_path / "camera" / "frames"
    directory.mkdir(parents=True)
    return directory


def frame(directory, timestamp, color):
    path = directory / f"{int(timestamp * 1000)}.jpg"
    with Image.new("RGB", (16, 16), color) as image:
        image.save(path)
    return path


def test_motion_clip_preserves_irregular_capture_intervals(buffer):
    for timestamp, color in [(95, "red"), (99, "green"), (102, "blue")]:
        frame(buffer, timestamp, color)
    path = eb.build_event_gif("camera", event_time=100, wait_post=0)
    with Image.open(path) as gif:
        durations = []
        for index in range(gif.n_frames):
            gif.seek(index)
            durations.append(gif.info["duration"])
    assert durations == [4000, 3000, 500]


def test_corrupt_frame_does_not_shorten_motion_timeline(buffer):
    frame(buffer, 95, "red")
    (buffer / "98000.jpg").write_bytes(b"bad jpeg")
    frame(buffer, 102, "blue")
    path = eb.build_event_gif("camera", event_time=100, wait_post=0)
    with Image.open(path) as gif:
        assert gif.n_frames == 2
        assert gif.info["duration"] == 7000


def test_old_still_is_not_relabelled_as_current_event(buffer):
    frame(buffer, 10, "red")
    assert eb.build_event_gif("camera", event_time=100, wait_post=0) is None


def test_sampling_preserves_first_and_latest_frame():
    frames = [Path(str(i)) for i in range(121)]
    sampled = eb._sample_frames(frames, 60)
    assert len(sampled) == 60
    assert sampled[0] == frames[0]
    assert sampled[-1] == frames[-1]
    assert len(set(sampled)) == 60
