import subprocess
import sys
import time
from unittest.mock import Mock

import psutil

from app.utils import scheduling


def spawn_stubborn_child(pid_file):
    """Stand in for a browser that survives its capture worker."""
    code = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    subprocess.Popen([sys.executable, "-c", code])
    time.sleep(60)


def running(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_timeout_stops_owned_child_but_preserves_unrelated_process(
    monkeypatch, tmp_path
):
    pid_file = tmp_path / "child.pid"
    sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(scheduling, "is_system_online", lambda: True)
    monkeypatch.setattr(scheduling.psutil, "cpu_percent", lambda **kw: 0)
    monkeypatch.setattr(scheduling.psutil, "virtual_memory", lambda: Mock(percent=0))
    monkeypatch.setattr(scheduling, "register_job_failure", Mock())
    monkeypatch.setattr(scheduling, "active_jobs", {})
    monkeypatch.setattr(scheduling, "job_backoff_until", {})
    monkeypatch.setattr(scheduling, "job_circuit_open_until", {})
    try:
        assert (
            scheduling.run_with_timeout(spawn_stubborn_child, (pid_file,), timeout=1)
            is False
        )
        assert pid_file.exists(), "worker must launch child before timing out"
        assert not running(
            int(pid_file.read_text())
        ), "timed-out worker left child alive"
        assert sibling.poll() is None, "cleanup crossed worker ownership boundary"
    finally:
        if pid_file.exists():
            try:
                psutil.Process(int(pid_file.read_text())).kill()
            except psutil.NoSuchProcess:
                pass
        sibling.kill()
        sibling.wait(timeout=3)
