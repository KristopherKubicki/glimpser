"""Stream bursts must not destroy another capture or the last published image."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.utils import screenshots as ss


@pytest.fixture
def stream_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "_check_ffmpeg", lambda: True)
    monkeypatch.setattr(ss, "_probe_stream_with_ffprobe", lambda *args: True)
    monkeypatch.setattr(ss, "PREFLIGHT_FFMPEG_NULL_PROBE", False)
    monkeypatch.setattr(ss, "FFMPEG_HWACCEL", "false")
    monkeypatch.setattr(ss, "_captured_frame_rejection_reason", lambda image: None)
    monkeypatch.setattr(ss, "_has_repeated_stream_rows", lambda image: False)
    monkeypatch.setattr(ss, "_stream_frame_quality_score", lambda image: 1)
    monkeypatch.setattr(
        ss, "_postprocess_still_image", lambda image, *a, **k: image.copy()
    )
    monkeypatch.setattr(ss, "add_timestamp", lambda *a, **k: None)
    monkeypatch.setattr(ss, "record_preflight_backoff", lambda *a: None)
    output = tmp_path / "latest.png"
    Image.new("RGB", (64, 64), "red").save(output)
    before = output.read_bytes()
    directories = []

    def produce(command, **kwargs):
        frame = Path(command[-1].replace("%03d", "001"))
        directories.append(frame.parent)
        Image.new("RGB", (64, 64), "blue").save(frame)

    monkeypatch.setattr(ss.subprocess, "run", produce)
    return output, before, directories, produce


def capture(output):
    return ss.capture_frame_from_stream(
        "https://example.test/video", str(output), name="publication-test"
    )


@pytest.mark.parametrize("failure", ["rejected", "postprocess", "timestamp", "corrupt"])
def test_failed_capture_preserves_last_good_image(monkeypatch, stream_capture, failure):
    output, before, directories, _ = stream_capture

    def fail(*args, **kwargs):
        raise OSError("injected processing failure")

    if failure == "rejected":
        monkeypatch.setattr(
            ss, "_captured_frame_rejection_reason", lambda image: "blank"
        )
    elif failure == "postprocess":
        monkeypatch.setattr(ss, "_postprocess_still_image", fail)
    elif failure == "timestamp":
        monkeypatch.setattr(ss, "add_timestamp", fail)
    else:
        monkeypatch.setattr(
            ss, "add_timestamp", lambda path, **k: Path(path).write_bytes(b"broken")
        )

    assert capture(output) is False
    assert output.read_bytes() == before
    assert all(not path.exists() for path in directories)
    assert list(output.parent.iterdir()) == [output]


def test_publication_happens_only_after_timestamp(monkeypatch, stream_capture):
    output, before, directories, _ = stream_capture

    def timestamp(path, **kwargs):
        assert output.read_bytes() == before
        assert Path(path).parent == output.parent
        Image.new("RGB", (64, 64), "green").save(path)

    monkeypatch.setattr(ss, "add_timestamp", timestamp)
    assert capture(output) is True
    with Image.open(output) as image:
        assert image.getpixel((0, 0)) == (0, 128, 0)
    assert all(not path.exists() for path in directories)
    assert list(output.parent.iterdir()) == [output]


def test_overlapping_same_feed_bursts_keep_their_own_frames(
    monkeypatch, stream_capture
):
    output, _, directories, produce = stream_capture

    def overlapping_capture(command, **kwargs):
        produce(command, **kwargs)
        if len(directories) == 1:
            first_frame = Path(command[-1].replace("%03d", "001"))
            assert capture(output.parent / "second.png") is True
            assert first_frame.exists()

    monkeypatch.setattr(ss.subprocess, "run", overlapping_capture)
    assert capture(output) is True
    assert len(set(directories)) == 2
    assert all(not path.exists() for path in directories)


def test_timeout_cleans_partial_burst(monkeypatch, stream_capture):
    output, before, directories, produce = stream_capture

    def timeout(command, **kwargs):
        produce(command, **kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(ss.subprocess, "run", timeout)
    assert capture(output) is False
    assert output.read_bytes() == before
    assert all(not path.exists() for path in directories)


def test_failed_replace_cleans_staging_file(monkeypatch, stream_capture):
    output, before, directories, _ = stream_capture

    def fail(*args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(ss.os, "replace", fail)
    assert capture(output) is False
    assert output.read_bytes() == before
    assert list(output.parent.iterdir()) == [output]
    assert all(not path.exists() for path in directories)


@pytest.mark.parametrize("elapsed", [0, 7, 10, 12])
def test_software_retry_shares_deadline_and_discards_failed_burst(
    monkeypatch, stream_capture, elapsed
):
    output, before, directories, produce = stream_capture
    monkeypatch.setattr(ss, "FFMPEG_HWACCEL", "cuda")
    clock = [100.0]
    monkeypatch.setattr(ss.time, "monotonic", lambda: clock[0])
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        if len(calls) == 1:
            produce(command, **kwargs)
            # A failed decoder can leave extra frames beyond the new burst.
            Image.new("RGB", (64, 64), "green").save(command[-1].replace("%03d", "099"))
            clock[0] += elapsed
            raise subprocess.CalledProcessError(
                1, command, stderr=b"Cannot load libcuda.so.1"
            )
        assert not list(Path(command[-1]).parent.iterdir())
        produce(command, **kwargs)

    monkeypatch.setattr(ss.subprocess, "run", run)
    result = ss.capture_frame_from_stream(
        "https://example.test/video", str(output), timeout=10, name="retry-test"
    )
    if elapsed >= 10:
        assert result is False
        assert len(calls) == 1
        assert output.read_bytes() == before
    else:
        assert result is True
        assert len(calls) == 2
        assert calls[1][1] == 10 - elapsed
        assert "-hwaccel" not in calls[1][0]
        with Image.open(output) as image:
            assert image.getpixel((0, 0)) == (0, 0, 255)
    assert all(not path.exists() for path in directories)


def test_stream_decoder_never_reads_worker_stdin(monkeypatch, stream_capture):
    output, _, _, produce = stream_capture
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        produce(command, **kwargs)

    monkeypatch.setattr(ss.subprocess, "run", run)
    assert capture(output) is True
    assert all("-nostdin" in command for command in commands)
