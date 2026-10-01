import subprocess
import sys
import threading

import pytest

from app import routes


@pytest.fixture
def stream_child(monkeypatch):
    children = []
    popen = subprocess.Popen
    monkeypatch.setattr(routes, "build_live_ffmpeg_command", lambda *a, **k: [])
    monkeypatch.setattr(routes.live_caps, "record_success", lambda *a, **k: None)
    monkeypatch.setattr(routes.live_caps, "record_failure", lambda *a, **k: None)
    monkeypatch.setattr(routes, "live_host_key", lambda _: None)

    def start(code):
        child = popen(
            [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        children.append(child)
        monkeypatch.setattr(routes.subprocess, "Popen", lambda *a, **k: child)
        return child

    yield start
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)
        child.stdout.close()
        child.stderr.close()


def first_with_deadline(generator, child):
    result = []

    def consume():
        try:
            result.append(next(generator))
        except StopIteration:
            result.append(None)
        except BaseException as exc:
            result.append(exc)

    worker = threading.Thread(target=consume, daemon=True)
    worker.start()
    worker.join(3)
    finished = not worker.is_alive()
    if not finished:
        child.kill()
        child.wait(timeout=3)
        worker.join(3)
    assert finished, "stream blocked past its no-output deadline"
    return result[0]


def test_silent_encoder_timeout_reaps_process_and_closes_pipes(stream_child):
    child = stream_child("import time; time.sleep(30)")
    generator = routes.generate_live_stream(
        "rtsp://example.test/live", max_no_output_seconds=0.05, max_no_output_failures=1
    )
    assert first_with_deadline(generator, child) is None
    assert child.poll() is not None
    assert child.stdout.closed and child.stderr.closed


def test_stderr_flood_cannot_block_video_and_disconnect_reaps_encoder(stream_child):
    child = stream_child(
        "import os,time; os.write(2,b'x' * 1048576); os.write(1,b'frame'); time.sleep(30)"
    )
    generator = routes.generate_live_stream(
        "rtsp://example.test/live", max_no_output_seconds=1, max_no_output_failures=1
    )
    try:
        assert first_with_deadline(generator, child) == b"frame"
    finally:
        generator.close()
    assert child.poll() is not None
    assert child.stdout.closed and child.stderr.closed


def test_continuous_diagnostics_do_not_reset_video_deadline(stream_child):
    child = stream_child(
        "import os,time\nwhile True:\n os.write(2,b'warning\\n' * 128); time.sleep(.001)"
    )
    generator = routes.generate_live_stream(
        "rtsp://example.test/live", max_no_output_seconds=0.05, max_no_output_failures=1
    )
    assert first_with_deadline(generator, child) is None
    assert child.poll() is not None
