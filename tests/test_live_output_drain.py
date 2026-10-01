import subprocess
import sys
import tempfile

import pytest

from app import routes


@pytest.mark.parametrize("stderr_first", [False, True])
def test_exited_encoder_is_drained_through_stdout_eof(monkeypatch, stderr_first):
    # A real completed child with more output than one read. A file-backed pipe
    # surrogate makes the exited-but-unread state deterministic without timing.
    payload = bytes(range(256)) * 1024
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as diagnostic:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes(range(256))*1024)",
            ],
            stdout=output,
            stderr=diagnostic,
        )
        child.wait(timeout=3)
        output.seek(0)
        diagnostic.seek(0)
        child.stdout = output
        child.stderr = diagnostic
        monkeypatch.setattr(routes.subprocess, "Popen", lambda *a, **k: child)
        monkeypatch.setattr(routes, "build_live_ffmpeg_command", lambda *a, **k: [])
        monkeypatch.setattr(routes, "live_host_key", lambda _: None)
        monkeypatch.setattr(routes.live_caps, "record_success", lambda *a, **k: None)
        if stderr_first:
            real_select = routes.select.select
            first = True

            def select(readers, *args):
                nonlocal first
                if first:
                    first = False
                    return [diagnostic], [], []
                return real_select(readers, *args)

            monkeypatch.setattr(routes.select, "select", select)
        chunks = list(
            routes.generate_live_stream(
                "rtsp://example.test/live", max_no_output_seconds=1
            )
        )
        assert b"".join(chunks) == payload
        assert len(chunks) >= 4
        assert child.stdout.closed and child.stderr.closed


def test_real_pipe_keeps_bytes_written_before_exit_while_consumer_pauses(monkeypatch):
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os; os.write(1,b'A'*1024); os.read(0,1); os.write(1,b'B'*1024)",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    monkeypatch.setattr(routes.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(routes, "build_live_ffmpeg_command", lambda *a, **k: [])
    monkeypatch.setattr(routes, "live_host_key", lambda _: None)
    monkeypatch.setattr(routes.live_caps, "record_success", lambda *a, **k: None)
    generator = routes.generate_live_stream(
        "rtsp://example.test/live", max_no_output_seconds=1
    )
    try:
        assert next(generator) == b"A" * 1024
        child.stdin.write(b"x")
        child.stdin.flush()
        child.wait(timeout=3)
        assert b"".join(generator) == b"B" * 1024
    finally:
        generator.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)
        child.stdin.close()
