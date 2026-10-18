"""Stream encoder input with bounded output, execution and process cleanup."""

import logging
import os
import selectors
import subprocess
import time
from pathlib import Path


def _stop_encoder(process, grace: float) -> None:
    """Reap a failed encoder without waiting forever on a kernel-stuck task."""
    for stop in (process.terminate, process.kill):
        if process.poll() is not None:
            return
        try:
            stop()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            pass
    logging.error(
        "Encoder PID %s survived SIGKILL; capture /proc/%s/task/*/{stat,stack,status} "
        "and kernel logs before recovery",
        process.pid,
        process.pid,
    )

    # Preserve thread-level evidence before a future restart destroys it. Never
    # log cmdline/environ: encoder arguments can contain signed camera URLs.
    try:
        tasks = sorted(Path(f"/proc/{process.pid}/task").iterdir())[:16]
        for task in tasks:
            for name in ("stat", "stack", "status"):
                try:
                    details = (task / name).read_text()[:8192]
                except OSError as exc:
                    details = f"unavailable: {exc.strerror}"
                logging.error(
                    "Stuck encoder thread %s %s: %s", task.name, name, details
                )
    except OSError:
        pass


def stream_encoder_frames(command, frame_files, timeout=120, stop_grace=2):
    """Return process/output after encoding, or raise within a bounded deadline.

    Drain both output pipes while feeding frames to avoid pipe-buffer deadlocks.
    Retain only their final 64 KiB. The deadline also covers encoders that close
    every pipe but never exit. Local frame reads must themselves remain healthy.
    """
    if timeout <= 0 or stop_grace <= 0:
        raise ValueError("Encoder timeout and stop grace must be positive")

    def frame_chunks():
        for frame in frame_files:
            with open(frame, "rb") as img:
                while chunk := img.read(65536):
                    yield chunk

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    deadline = time.monotonic() + timeout
    chunks = frame_chunks()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    pending = b""

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise subprocess.TimeoutExpired(
                command,
                timeout,
                output=bytes(output["stdout"]),
                stderr=bytes(output["stderr"]),
            )
        return seconds

    deadline_error = None
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            while selector.get_map():
                for key, _ in selector.select(timeout=remaining()):
                    if key.data != "stdin":
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        tail = output[key.data]
                        tail.extend(chunk)
                        del tail[:-65536]
                        continue
                    if not pending:
                        pending = next(chunks, b"")
                    if not pending:
                        selector.unregister(process.stdin)
                        process.stdin.close()
                        continue
                    try:
                        pending = pending[os.write(key.fd, pending) :]
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        # Preserve stderr for the caller's hardware fallback.
                        selector.unregister(process.stdin)
                        process.stdin.close()
            process.wait(timeout=remaining())
    except subprocess.TimeoutExpired as exc:
        deadline_error = exc
        raise
    finally:
        chunks.close()
        try:
            _stop_encoder(process, stop_grace)
            if deadline_error is not None:
                # Preserve cleanup evidence without extending the signal budget.
                deadline_error.encoder_stopped = process.poll() is not None
        finally:
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
    return process, bytes(output["stdout"]), bytes(output["stderr"])


def run_encoder_command(command, timeout=30):
    """Run a file-based encoder with bounded diagnostics and cleanup."""
    process, stdout, stderr = stream_encoder_frames(command, [], timeout=timeout)
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )
