# app/utils/system_metrics.py
"""Background system metrics collection and log caching utilities."""

from __future__ import annotations

import datetime
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

import psutil

from app.config import FFMPEG_HWACCEL, FFMPEG_PATH, LOGGING_PATH, get_setting

system_metrics: Dict[str, Any] = {
    "cpu_usage": 0.0,
    "memory_usage": 0.0,
    "thread_count": 0,
    "start_time": time.time(),
    "top_threads": [],
}

stop_event = threading.Event()
metrics_thread: threading.Thread | None = None
log_caching_thread: threading.Thread | None = None
thread_cpu_times: Dict[int, float] = {}
last_thread_sample = time.time()
child_procs: List[psutil.Process] = []

# Cache ffmpeg version after the first lookup to avoid repeated subprocess calls.
FFMPEG_VERSION: str | None = None
# Cache result of ffmpeg hwaccel capability detection
FFMPEG_GPU_SUPPORT: Optional[bool] = None

log_cache: deque = deque(maxlen=10000)
log_cache_lock = threading.Lock()


def ffmpeg_version() -> str:
    """Return the installed FFmpeg version or 'unavailable'."""

    global FFMPEG_VERSION
    if FFMPEG_VERSION is not None:
        return FFMPEG_VERSION
    try:
        output = subprocess.check_output(
            [FFMPEG_PATH, "-version"], stderr=subprocess.STDOUT, timeout=2
        ).decode()
        first = output.splitlines()[0]
        match = re.search(r"ffmpeg version\s+([^\s]+)", first)
        FFMPEG_VERSION = match.group(1) if match else first
    except Exception:
        FFMPEG_VERSION = "unavailable"
    return FFMPEG_VERSION


def machine_supports_hwaccel() -> bool:
    """Return ``True`` if GPU devices appear to be available."""

    return os.path.exists("/dev/dri") or shutil.which("nvidia-smi") is not None


def ffmpeg_supports_hwaccel() -> bool:
    """Return ``True`` if ``ffmpeg`` reports any hardware acceleration methods."""

    global FFMPEG_GPU_SUPPORT
    if FFMPEG_GPU_SUPPORT is not None:
        return FFMPEG_GPU_SUPPORT
    try:
        output = subprocess.check_output(
            [FFMPEG_PATH, "-hwaccels"], stderr=subprocess.STDOUT, timeout=2
        ).decode()
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        FFMPEG_GPU_SUPPORT = len(lines) > 1
    except Exception:
        FFMPEG_GPU_SUPPORT = False
    return FFMPEG_GPU_SUPPORT


def collect_system_metrics() -> None:
    """Continuously update CPU and memory metrics."""

    psutil.cpu_percent(interval=None)
    proc = psutil.Process()
    global thread_cpu_times, last_thread_sample, child_procs
    proc.cpu_percent(interval=None)
    child_procs = proc.children(recursive=True)
    for child in child_procs:
        try:
            child.cpu_percent(interval=None)
        except Exception:
            continue
    while not stop_event.is_set():
        start = time.time()
        system_metrics["cpu_usage"] = psutil.cpu_percent(interval=None)
        system_metrics["memory_usage"] = psutil.virtual_memory().percent
        system_metrics["thread_count"] = threading.active_count()

        interval = start - last_thread_sample or 1
        current = {t.id: t.user_time + t.system_time for t in proc.threads()}
        usages = []
        for tid, ttime in current.items():
            prev = thread_cpu_times.get(tid, ttime)
            cpu = ((ttime - prev) / interval) * 100 / psutil.cpu_count()
            name = next(
                (t.name for t in threading.enumerate() if t.ident == tid),
                f"Thread {tid}",
            )
            usages.append({"id": tid, "name": name, "cpu": round(cpu, 1)})
        thread_cpu_times = current
        last_thread_sample = start
        for child in proc.children(recursive=True):
            try:
                cpu = child.cpu_percent(interval=None)
                cmd = child.cmdline()
                name = (
                    os.path.basename(cmd[0]) if cmd else os.path.basename(child.name())
                )
                if cpu:
                    usages.append({"id": child.pid, "name": name, "cpu": round(cpu, 1)})
            except Exception:
                continue
        usages.sort(key=lambda x: x["cpu"], reverse=True)
        system_metrics["top_threads"] = usages[:10]
        stop_event.wait(5)


def start_metrics_collection() -> None:
    """Spawn the background metrics collection thread."""

    global metrics_thread
    metrics_thread = threading.Thread(target=collect_system_metrics, daemon=True)
    metrics_thread.start()


def get_system_metrics() -> Dict[str, Any]:
    """Return the current system metrics summary."""

    uptime = time.time() - system_metrics["start_time"]
    disk_usage = psutil.disk_usage("/").percent
    process = psutil.Process()
    if hasattr(process, "num_fds"):
        open_files = process.num_fds()
    else:
        open_files = len(process.open_files())
    ffmpeg_path = shutil.which(FFMPEG_PATH) or FFMPEG_PATH
    ffmpeg_version_str = ffmpeg_version()
    ffmpeg_gpu_support = (
        ffmpeg_supports_hwaccel() if FFMPEG_GPU_SUPPORT is None else FFMPEG_GPU_SUPPORT
    )
    return {
        "cpu_usage": round(system_metrics["cpu_usage"], 1),
        "memory_usage": round(system_metrics["memory_usage"], 1),
        "disk_usage": round(disk_usage, 1),
        "open_files": open_files,
        "thread_count": system_metrics["thread_count"],
        "top_threads": system_metrics.get("top_threads", []),
        "uptime": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "ffmpeg_version": ffmpeg_version_str,
        "ffmpeg_path": ffmpeg_path,
        "machine_hwaccel": machine_supports_hwaccel(),
        "ffmpeg_hwaccel": ffmpeg_gpu_support,
        "ffmpeg_gpu_support": ffmpeg_gpu_support,
        "hwaccel_enabled": bool(FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false"),
        "gpu_support": machine_supports_hwaccel(),
        "ffmpeg_gpu_enabled": bool(
            FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false"
        ),
        "danger_mode": get_setting("DANGER_MODE", "True") == "True",
    }


def cache_logs() -> None:
    """Continuously read ``LOGGING_PATH`` into ``log_cache``."""

    log_file_path = LOGGING_PATH
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    open(log_file_path, "a").close()

    try:
        with open(log_file_path, "r") as file:
            file.seek(0, os.SEEK_END)
            while True:
                new_log = file.readline()
                if not new_log:
                    if stop_event.is_set():
                        break
                    time.sleep(1)
                    file.seek(0, os.SEEK_END)
                    continue

                with log_cache_lock:
                    truncated_log = (
                        new_log[:500] + "..." if len(new_log) > 500 else new_log
                    )
                    log_parts = truncated_log.strip().split(" - ", 3)
                    if len(log_parts) >= 4:
                        timestamp_str, log_level, log_source, log_message = log_parts
                        try:
                            timestamp = datetime.datetime.strptime(
                                timestamp_str, "%Y-%m-%d %H:%M:%S,%f"
                            )
                            log_cache.append(
                                {
                                    "timestamp": timestamp,
                                    "level": log_level,
                                    "source": log_source,
                                    "message": log_message,
                                }
                            )
                        except ValueError:
                            continue
    except Exception as e:
        logging.error("Error in cache_logs: %s", e)


def start_log_caching() -> None:
    """Start the background log caching thread."""

    global log_caching_thread
    log_caching_thread = threading.Thread(target=cache_logs, daemon=True)
    log_caching_thread.start()


# The background thread itself handles continuous log caching and avoids
# spawning additional threads on scheduler restarts.


def stop_background_tasks() -> None:
    """Signal background threads to exit and wait for them."""

    stop_event.set()
    for t in (metrics_thread, log_caching_thread):
        if t is not None:
            t.join(timeout=1)
