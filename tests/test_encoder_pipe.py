"""Exercise encoder failure modes with real pipes and real child processes."""

import subprocess
import sys
import time

import pytest

from app.utils import encoder_pipe


@pytest.fixture
def children(monkeypatch):
    launched = []
    original = subprocess.Popen

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr(encoder_pipe.subprocess, "Popen", launch)
    yield launched
    for process in launched:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


def run(code, frames, **kwargs):
    return encoder_pipe.stream_encoder_frames(
        [sys.executable, "-c", code], frames, **kwargs
    )


def assert_reaped(children):
    assert children
    for process in children:
        assert process.poll() is not None
        assert all(p.closed for p in (process.stdin, process.stdout, process.stderr))


def test_output_flood_does_not_deadlock(tmp_path, children):
    frame = tmp_path / "frame"
    frame.write_bytes(b"x" * 1500000)
    _, out, err = run(
        "import os,sys; os.write(2,b'E'*1048576); os.write(1,b'O'*1048576); "
        "print(len(sys.stdin.buffer.read()))",
        [frame],
        timeout=3,
    )
    assert out.endswith(b"1500000\n")
    assert len(out) <= 65536 and len(err) == 65536
    assert_reaped(children)


@pytest.mark.parametrize(
    "code",
    [
        "import time; time.sleep(30)",
        "import os,time; os.close(0); os.close(1); os.close(2); time.sleep(30)",
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)",
    ],
)
def test_stalled_encoder_is_bounded_and_reaped(tmp_path, children, code):
    frame = tmp_path / "frame"
    frame.write_bytes(b"x" * 1500000)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run(code, [frame], timeout=0.4, stop_grace=0.2)
    assert time.monotonic() - started < 2
    assert_reaped(children)


def test_missing_input_reaps_encoder(tmp_path, children):
    with pytest.raises(FileNotFoundError):
        run("import time; time.sleep(30)", [tmp_path / "missing"], stop_grace=0.2)
    assert_reaped(children)


def test_early_failure_preserves_fallback_diagnostic(tmp_path, children):
    frame = tmp_path / "frame"
    frame.write_bytes(b"x" * 1500000)
    process, _, err = run(
        "import sys; sys.stderr.write('CUDA_ERROR_NO_DEVICE'); sys.exit(1)",
        [frame],
        timeout=2,
    )
    assert process.returncode == 1
    assert err == b"CUDA_ERROR_NO_DEVICE"
    assert_reaped(children)


def test_unkillable_process_cleanup_is_bounded(caplog):
    class Stuck:
        pid = 123
        signals = []
        waits = []

        def poll(self):
            return None

        def terminate(self):
            self.signals.append("TERM")

        def kill(self):
            self.signals.append("KILL")

        def wait(self, timeout):
            self.waits.append(timeout)
            raise subprocess.TimeoutExpired("encoder", timeout)

    process = Stuck()
    encoder_pipe._stop_encoder(process, 0.2)
    assert process.signals == ["TERM", "KILL"]
    assert process.waits == [0.2, 0.2]
    assert "survived SIGKILL" in caplog.text


def test_file_command_returns_completed_process(children):
    command = [sys.executable, "-c", "import sys; print('done'); sys.exit(7)"]
    result = encoder_pipe.run_encoder_command(command, timeout=2)
    assert result.args == command
    assert result.returncode == 7
    assert result.stdout == "done\n"
    assert_reaped(children)


def test_file_command_timeout_is_bounded(children):
    with pytest.raises(subprocess.TimeoutExpired):
        encoder_pipe.run_encoder_command(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2
        )
    assert_reaped(children)
