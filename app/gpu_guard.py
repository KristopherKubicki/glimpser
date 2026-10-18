"""Bound FFmpeg cleanup and share device-loss quarantine across workers."""

import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .encoder_pipe import stream_encoder_frames

_local_fault = None


def _state_path():
    return Path.home() / ".local/state/glimpser/gpu-fault.json"


def _boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def gpu_fault():
    """Read small shared state, never query an unresponsive GPU driver."""
    if _local_fault is not None:
        return _local_fault
    try:
        state = json.loads(_state_path().read_text())
        if not isinstance(state, dict) or "boot_id" not in state:
            raise ValueError("invalid state")
        if state["boot_id"] == _boot_id():
            return state
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        return {"reason": "GPU quarantine state unreadable"}
    return None


def _quarantine(reason):
    global _local_fault
    state = {
        "boot_id": _boot_id(),
        "reason": reason,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    _local_fault = state
    target = _state_path()
    temp = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=target.parent, prefix="gpu-fault-", delete=False
        ) as stream:
            temp = Path(stream.name)
            json.dump(state, stream)
            stream.write("\n")
        os.replace(temp, target)
    except OSError:
        logging.error("GPU quarantine could not be persisted; this worker is disabled")
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    logging.error("GPU quarantined; future captures use software: %s", reason)


def acceleration_status(startup_status):
    """Distinguish startup capability from subsequently observed failure."""
    from . import nvenc_budget

    startup_status = {**startup_status, "archive_encoding": nvenc_budget.status()}
    fault = gpu_fault()
    if fault:
        return {
            **startup_status,
            "effective": "false",
            "status": "failed",
            "reason": fault["reason"],
            "observed_at": fault.get("observed_at"),
            "basis": "observed_gpu_fault",
        }
    return {**startup_status, "basis": "startup_capability_check"}


def _uses_cuda(command):
    return (
        any(
            value == "-hwaccel" and command[i + 1].lower() == "cuda"
            for i, value in enumerate(command[:-1])
        )
        or "h264_nvenc" in command
    )


def _software_command(command):
    result = []
    index = 0
    while index < len(command):
        if command[index] == "-hwaccel" and index + 1 < len(command):
            index += 2
            continue
        result.append("libx264" if command[index] == "h264_nvenc" else command[index])
        index += 1
    return result


def _device_lost(stderr):
    lower = stderr.lower()
    return any(
        marker in lower
        for marker in (
            b"cuda_error_no_device",
            b"cuda_error_unknown",
            b"no cuda-capable device",
            b"gpu has fallen off the bus",
            b"cannot load libcuda",
            b"could not dynamically load cuda",
        )
    )


def _redact(stderr):
    # FFmpeg embeds input URLs, including RTSP userinfo, in diagnostic output.
    return re.sub(rb"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+", b"[URL]", stderr)


def _attempt(command, timeout):
    try:
        return stream_encoder_frames(command, [], timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        sanitized = subprocess.TimeoutExpired(
            [command[0], "[arguments redacted]"],
            timeout,
            output=exc.output,
            stderr=_redact(exc.stderr or b""),
        )
        sanitized.encoder_stopped = getattr(exc, "encoder_stopped", False)
        raise sanitized from None


def run_capture_command(
    command, *, timeout=30, check=False, stdout=None, stderr=None, text=False
):
    """Run at most one GPU attempt and one software retry, both bounded.

    A CUDA timeout is quarantined conservatively because a stuck driver can
    prevent normal termination. A stream error alone never disables the GPU.
    The existing bounded runner collects process metadata if SIGKILL fails.
    """
    if stdout not in (None, subprocess.PIPE) or stderr not in (None, subprocess.PIPE):
        raise ValueError("Only captured FFmpeg output is supported")
    original = list(command)
    accelerated = _uses_cuda(original)
    current = _software_command(original) if accelerated and gpu_fault() else original
    try:
        process, out, err = _attempt(current, timeout)
    except subprocess.TimeoutExpired as exc:
        if _uses_cuda(current):
            _quarantine("CUDA operation exceeded its deadline")
            current = _software_command(original)
            process, out, err = _attempt(current, timeout)
        else:
            # Keep source credentials out of exception formatting/logging.
            raise subprocess.TimeoutExpired(
                [original[0], "[arguments redacted]"],
                timeout,
                output=exc.output,
                stderr=_redact(exc.stderr or b""),
            ) from None
    else:
        if process.returncode and _uses_cuda(current) and _device_lost(err):
            _quarantine("CUDA device became unavailable")
            current = _software_command(original)
            process, out, err = _attempt(current, timeout)
    err = _redact(err)
    result = subprocess.CompletedProcess(
        current,
        process.returncode,
        out.decode(errors="replace") if text else out,
        err.decode(errors="replace") if text else err,
    )
    if check and result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode,
            [original[0], "[arguments redacted]"],
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def run_encoder_command(command, timeout=30):
    """Text-output adapter for the existing archive runner."""
    from . import nvenc_budget

    candidate = nvenc_budget.nvenc_command(command) if nvenc_budget.enabled() else None
    if candidate is not None and not gpu_fault():
        with nvenc_budget.lease() as admitted:
            if admitted:
                try:
                    process, out, err = _attempt(candidate, min(timeout, 15))
                    if not process.returncode:
                        nvenc_budget.record_success()
                        logging.info("Budgeted NVENC archive encode completed")
                        return subprocess.CompletedProcess(
                            candidate,
                            0,
                            out.decode(errors="replace"),
                            _redact(err).decode(errors="replace"),
                        )
                    if _device_lost(err):
                        _quarantine("NVENC device became unavailable")
                except subprocess.TimeoutExpired as exc:
                    if not getattr(exc, "encoder_stopped", False) or _device_lost(
                        exc.stderr or b""
                    ):
                        _quarantine("NVENC deadline with unsafe cleanup or device loss")
                    else:
                        logging.info(
                            "NVENC work budget reached; encoder stopped cleanly"
                        )
                logging.warning("Budgeted NVENC failed; retrying archive on CPU")
    return run_capture_command(command, timeout=timeout, text=True)
