"""Preflight must establish video presence without redundant decoder work."""

import json
import subprocess
from unittest.mock import Mock

import pytest

from app.utils import screenshots as ss


@pytest.mark.parametrize(
    "fps,expected", [(None, 8), ("0/1", 8), ("0/0", 8), ("1/1", 2), ("30/1", 8)]
)
def test_only_known_positive_low_fps_caps_bursts(monkeypatch, fps, expected):
    monkeypatch.setattr(ss, "_get_stream_fingerprint", lambda url: {"fps": fps})
    assert ss._apply_low_fps_rtsp_burst_cap("rtsp://example.test/video", 8, 1000) == (
        expected,
        1000,
    )


@pytest.mark.parametrize(
    "payload",
    [b"", b"broken", b"[]", b"null", b"{}", b'{"streams": []}', b'{"streams": [{}]}'],
)
def test_ffprobe_rejects_missing_video(monkeypatch, payload):
    monkeypatch.setattr(ss, "_check_ffprobe", lambda: True)
    monkeypatch.setattr(
        ss.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, payload, b""),
    )
    assert (
        ss._probe_stream_with_ffprobe("https://example.test/video", 10, "probe-test")
        is False
    )


def test_ffprobe_requests_and_caches_video_geometry(monkeypatch):
    monkeypatch.setattr(ss, "_check_ffprobe", lambda: True)
    stream = {
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "2/1",
        "pix_fmt": "yuv420p",
        "bit_rate": "800000",
    }
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, json.dumps({"streams": [stream]}).encode(), b""
        )
    )
    cache = Mock()
    monkeypatch.setattr(ss.subprocess, "run", run)
    monkeypatch.setattr(ss, "_set_stream_fingerprint", cache)
    assert (
        ss._probe_stream_with_ffprobe("https://example.test/video", 10, "probe-test")
        is True
    )
    command = run.call_args.args[0]
    entries = command[command.index("-show_entries") + 1]
    for field in stream:
        assert field in entries
    assert cache.call_args.args[1]["fps"] == "2/1"


def test_null_probe_requires_video_and_disables_stdin(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
    monkeypatch.setattr(ss.subprocess, "run", run)
    assert ss._ffmpeg_null_probe("https://example.test/video", 10, "probe-test") is True
    command = run.call_args.args[0]
    assert "-nostdin" in command
    assert command[command.index("-map") + 1] == "0:v:0"


@pytest.mark.parametrize("metadata_ok", [True, False])
def test_decode_probe_is_only_a_metadata_failure_fallback(
    monkeypatch, tmp_path, metadata_ok
):
    monkeypatch.setattr(ss, "_check_ffmpeg", lambda: True)
    monkeypatch.setattr(ss, "_probe_stream_with_ffprobe", lambda *a: metadata_ok)
    monkeypatch.setattr(ss, "PREFLIGHT_FFMPEG_NULL_PROBE", True)
    probe = Mock(return_value=True)
    monkeypatch.setattr(ss, "_ffmpeg_null_probe", probe)
    monkeypatch.setattr(ss.subprocess, "run", Mock())
    monkeypatch.setattr(ss, "_select_best_stream_frame", lambda *a: (None, None))
    ss.capture_frame_from_stream(
        "https://example.test/video", str(tmp_path / "frame.png")
    )
    assert probe.call_count == (0 if metadata_ok else 1)
