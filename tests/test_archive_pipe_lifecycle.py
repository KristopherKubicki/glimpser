import subprocess
import sys
import threading

from app.utils import video_archiver as archive


def run_child(monkeypatch, command, frames):
    """Bound regressions that would otherwise hang the test worker."""
    children = []
    results = []
    popen = subprocess.Popen

    def launch(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    def run():
        try:
            results.append(archive._pipe_ffmpeg_frames_once(command, frames))
        except BaseException as exc:
            results.append(exc)

    monkeypatch.setattr(archive.subprocess, "Popen", launch)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(4)
    finished = not worker.is_alive()
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
    worker.join(2)
    assert finished, "encoder pipes deadlocked"
    assert all(p.stdin.closed and p.stdout.closed and p.stderr.closed for p in children)
    return results[0]


def test_archive_drains_output_while_sending_frames(monkeypatch, tmp_path):
    frame = tmp_path / "frame.png"
    data = b"frame" * 300000
    frame.write_bytes(data)
    code = (
        "import os,sys; "
        "os.write(2,b'E'*1048576); os.write(1,b'O'*1048576); "
        "data=sys.stdin.buffer.read(); print(len(data))"
    )
    result = run_child(monkeypatch, [sys.executable, "-c", code], [frame])
    assert not isinstance(result, BaseException), repr(result)
    process, out, err = result
    assert process.returncode == 0
    assert out.endswith(f"{len(data)}\n".encode())
    assert 0 < len(out) <= 65536
    assert 0 < len(err) <= 65536


def test_archive_early_exit_preserves_error_for_fallback(monkeypatch, tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x" * 1048576)
    code = "import sys; sys.stderr.write('CUDA_ERROR_NO_DEVICE'); sys.exit(1)"
    result = run_child(monkeypatch, [sys.executable, "-c", code], [frame])
    assert not isinstance(result, BaseException), repr(result)
    process, out, err = result
    assert process.returncode == 1
    assert b"CUDA_ERROR_NO_DEVICE" in err


def test_archive_missing_frame_reaps_encoder(monkeypatch, tmp_path):
    result = run_child(
        monkeypatch,
        [sys.executable, "-c", "import time; time.sleep(30)"],
        [tmp_path / "missing.png"],
    )
    assert isinstance(result, FileNotFoundError)


def test_archive_success_sends_eof_without_flushing_closed_stdin(monkeypatch, tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"abc")
    result = run_child(
        monkeypatch,
        [sys.executable, "-c", "import sys; print(sys.stdin.buffer.read().hex())"],
        [frame],
    )
    assert not isinstance(result, BaseException), repr(result)
    assert result[1] == b"616263\n"


def test_early_hardware_failure_retries_all_frames(monkeypatch, tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x" * 1048576)
    monkeypatch.setattr(archive, "FFMPEG_HWACCEL", "cuda")
    code = (
        "import sys; "
        "hardware='-hwaccel' in sys.argv; "
        "sys.stderr.write('device creation failed' if hardware else ''); "
        "sys.exit(1) if hardware else None; "
        "data=sys.stdin.buffer.read(); sys.exit(0 if len(data)==1048576 else 2)"
    )
    process = archive.pipe_ffmpeg_frames(
        [sys.executable, "-c", code, "-hwaccel", "cuda"], [frame]
    )
    assert process.returncode == 0
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
