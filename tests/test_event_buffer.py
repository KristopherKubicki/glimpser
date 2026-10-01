from pathlib import Path

from PIL import Image

from app.utils import event_buffer


def _write_frame(root: Path, name: str, timestamp: float, color: tuple[int, int, int]):
    frame_dir = root / name / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    path = frame_dir / f"{int(timestamp * 1000)}.jpg"
    Image.new("RGB", (32, 18), color).save(path, "JPEG")
    return path


def test_build_event_gif_from_buffered_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(event_buffer, "EVENT_BUFFER_ROOT", tmp_path)
    monkeypatch.setattr(
        event_buffer,
        "get_template",
        lambda name: {
            "url": "http://192.168.1.30/snapshot.jpg",
            "event_buffer_fps": 1,
            "event_buffer_seconds": 60,
            "event_buffer_pre_seconds": 5,
            "event_buffer_post_seconds": 2,
            "event_buffer_width": 320,
        },
    )
    _write_frame(tmp_path, "FrontDoor", 95.0, (255, 0, 0))
    _write_frame(tmp_path, "FrontDoor", 100.0, (0, 255, 0))
    _write_frame(tmp_path, "FrontDoor", 101.0, (0, 0, 255))

    gif = event_buffer.build_event_gif("FrontDoor", event_time=100.0, wait_post=0)

    assert gif is not None
    assert gif.exists()
    with Image.open(gif) as image:
        assert image.format == "GIF"
        assert getattr(image, "is_animated", False)
        assert image.n_frames == 3


def test_tick_event_buffers_applies_failure_backoff(monkeypatch):
    event_buffer._STATE.clear()
    calls = []
    template = {
        "url": "http://192.168.1.30/snapshot.jpg",
        "event_buffer_enabled": True,
        "event_buffer_fps": 1,
        "event_buffer_seconds": 60,
        "event_buffer_backoff_seconds": 300,
    }
    monkeypatch.setattr(
        event_buffer, "_enabled_templates", lambda: {"FrontDoor": template}
    )

    def fail_capture(name, data, timestamp=None):
        calls.append((name, timestamp))
        raise ValueError("offline")

    monkeypatch.setattr(event_buffer, "capture_event_frame", fail_capture)

    first = event_buffer.tick_event_buffers(now=100.0)
    second = event_buffer.tick_event_buffers(now=101.0)

    assert first["failed"] == 1
    assert second["captured"] == second["failed"] == second["backoff"] == 0
    assert len(calls) == 1
    state = event_buffer._STATE["FrontDoor"]
    assert state.next_due > 101.0
    assert state.backoff_until == 0

    # Brief retries precede the long outage backoff after repeated failures.
    for _ in range(2):
        result = event_buffer.tick_event_buffers(now=state.next_due + 0.01)
        assert result["failed"] == 1
    assert len(calls) == 3
    assert state.backoff_until >= state.last_failure + 300
    result = event_buffer.tick_event_buffers(now=state.backoff_until - 1)
    assert result["backoff"] == 1
    assert len(calls) == 3
