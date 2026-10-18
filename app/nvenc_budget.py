"""Opt-in, serialized NVENC bursts with fresh external temperature telemetry."""

import fcntl
import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path

TELEMETRY = Path("/var/lib/glimpser-health/p4-latest.json")
STATE = Path.home() / ".local/state/glimpser"


def enabled():
    """Keep experimental encoding independent of hardware decoding."""
    return os.environ.get("FFMPEG_NVENC_BUDGETED", "false").lower() == "true"


def nvenc_command(command):
    """Convert only ordinary, overwriteable H.264 file-output commands."""
    command = list(command)
    if (
        command.count("libx264") != 1
        or "-y" not in command
        or "-hwaccel" in command
        or any("pipe:" in str(arg) for arg in command)
        or not command[-1].endswith(".mp4")
        or any(arg in command for arg in ("-x264-params", "-tune", "-filter_complex"))
    ):
        return None
    index = command.index("libx264")
    if index == 0 or command[index - 1] != "-c:v":
        return None
    command[index] = "h264_nvenc"
    for flag, replacement in (("-preset", "p4"),):
        if flag in command:
            command[command.index(flag) + 1] = replacement
    if "-preset" not in command:
        command[-1:-1] = ["-preset", "p4"]
    if "-crf" in command:
        command[command.index("-crf")] = "-cq"
    else:
        command[-1:-1] = ["-cq", "23"]
    if "-b:v" not in command:
        command[-1:-1] = ["-b:v", "0"]
    return command


@contextmanager
def lease():
    """Admit one job, at most every 75 seconds, below 60C; fail closed."""
    stream = None
    admitted = False
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        stream = (STATE / "nvenc-budget.lock").open("a+")
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        stamp = json.loads(TELEMETRY.read_text())
        age = time.time() - TELEMETRY.stat().st_mtime
        stream.seek(0)
        previous = json.loads(stream.read() or "{}")
        elapsed = time.monotonic() - previous.get("started", 0)
        if (
            stamp.get("boot_id") == boot
            and stamp.get("ok") is True
            and stamp.get("pstate") == "P8"
            and 0 <= age <= 20
            and 0 <= stamp["temperature_c"] < 60
            and (previous.get("boot_id") != boot or elapsed >= 75)
        ):
            stream.seek(0)
            stream.truncate()
            json.dump({"boot_id": boot, "started": time.monotonic()}, stream)
            stream.flush()
            admitted = True
    except (OSError, ValueError, KeyError, TypeError):
        admitted = False
    try:
        yield admitted
    finally:
        if stream is not None:
            stream.close()


def record_success():
    """Persist a small receipt showing actual successful GPU work."""
    record = {"completed_at": time.time(), "encoder": "h264_nvenc"}
    try:
        path = STATE / "nvenc-last-success.json"
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(record))
        temp.replace(path)
    except OSError:
        logging.warning("Could not persist NVENC success receipt")


def status():
    """Report policy separately from evidence of actual successful encoding."""
    result = {"mode": "budgeted_nvenc" if enabled() else "default"}
    if enabled():
        result.update(
            max_seconds=15,
            min_start_interval_seconds=75,
            start_below_c=60,
            required_idle_state="P8",
        )
        try:
            result["last_success"] = json.loads(
                (STATE / "nvenc-last-success.json").read_text()
            )
        except (OSError, ValueError):
            result["last_success"] = None
    return result
