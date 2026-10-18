"""Replay resources are released even when callers retain failed tracebacks."""

from pathlib import Path

import pytest
from PIL import Image

from app.utils import event_buffer as eb


@pytest.fixture
def frames(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "EVENT_BUFFER_ROOT", tmp_path)
    monkeypatch.setattr(
        eb,
        "get_template",
        lambda _: {
            "event_buffer_enabled": True,
            "event_buffer_pre_seconds": 5,
            "event_buffer_post_seconds": 1,
        },
    )
    directory = tmp_path / "camera" / "frames"
    directory.mkdir(parents=True)
    for stamp, color in [(98000, "red"), (99000, "blue")]:
        with Image.new("RGB", (16, 16), color) as image:
            image.save(directory / f"{stamp}.jpg")
    return tmp_path


def track_decoded(monkeypatch):
    decoded = []
    convert = Image.Image.convert

    def tracked(image, mode=None, *args, **kwargs):
        result = convert(image, mode, *args, **kwargs)
        if mode == "RGB":
            decoded.append(result)
        return result

    monkeypatch.setattr(Image.Image, "convert", tracked)
    return decoded


def assert_closed(images):
    assert len(images) >= 2
    for image in images:
        with pytest.raises(ValueError, match="closed"):
            image.getpixel((0, 0))


@pytest.mark.parametrize("kind", ["event", "recent"])
@pytest.mark.parametrize("failed", [False, True])
def test_decoded_pixels_released_on_success_and_encoder_failure(
    frames, monkeypatch, kind, failed
):
    decoded = track_decoded(monkeypatch)
    if failed:

        def fail_save(image, path, **kwargs):
            Path(path).write_bytes(b"partial")
            raise OSError("encoder failed")

        monkeypatch.setattr(Image.Image, "save", fail_save)

    def build():
        if kind == "event":
            return eb.build_event_gif("camera", event_time=100, wait_post=0)
        return eb.recent_replay("camera", now=100)

    if failed:
        with pytest.raises(OSError, match="encoder failed") as retained_exception:
            build()
        # Keep traceback locals alive; cleanup must not depend on GC.
        assert retained_exception.traceback
    else:
        result = build()
        assert result
        path = result if kind == "event" else result["path"]
        with Image.open(path) as gif:
            assert gif.n_frames == 2
    assert_closed(decoded)
    assert not list(frames.rglob("*.tmp"))


def test_rejected_stale_replay_releases_images(frames, monkeypatch):
    decoded = track_decoded(monkeypatch)
    assert eb.recent_replay("camera", now=120) is None
    assert_closed(decoded)


def test_failed_alert_write_preserves_existing_gif(frames, monkeypatch):
    old = eb.build_event_gif("camera", event_time=100, wait_post=0)
    original = old.read_bytes()

    def fail_save(image, path, **kwargs):
        assert Path(path) != old.with_suffix(".gif.tmp")
        Path(path).write_bytes(b"partial")
        raise OSError("encoder failed")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    with pytest.raises(OSError):
        eb.build_event_gif("camera", event_time=100, wait_post=0)
    assert old.read_bytes() == original
    assert not list(frames.rglob("*.tmp"))


def test_wait_loop_never_passes_negative_sleep(frames, monkeypatch):
    clock = iter([100.9, 101.1])
    monkeypatch.setattr(eb.time, "time", lambda: next(clock))
    sleeps = []

    def sleep(seconds):
        assert seconds > 0
        sleeps.append(seconds)

    monkeypatch.setattr(eb.time, "sleep", sleep)
    monkeypatch.setattr(eb, "_frames_for_window", lambda *args: [])
    monkeypatch.setattr(eb, "_frame_dir", lambda _: frames / "missing")
    assert eb.build_event_gif("camera", event_time=100, wait_post=1) is None
    assert sleeps == [pytest.approx(0.1)]
