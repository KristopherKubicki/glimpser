"""Exercise real process exit without starting the application or scheduler."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "mode, expected", [("clean", 0), ("cleanup_hung", 1), ("worker_hung", 1)]
)
def test_signal_shutdown_has_bounded_process_exit(mode, expected):
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text())
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "_enforce_shutdown_deadline",
            "_start_shutdown_deadline",
            "graceful_shutdown",
        }
    ]
    assert len(selected) == 3
    functions = ast.unparse(ast.Module(body=selected, type_ignores=[]))
    setup = """
import logging, os, signal, sys, threading, time
from types import SimpleNamespace
os.environ.pop("GLIMPSER_HARD_EXIT_ON_SIGNAL", None)
SHUTDOWN_DEADLINE_SECONDS = 0.2
_shutdown_signaled = False
_shutdown_signal_lock = threading.Lock()
scheduler = SimpleNamespace(pause=lambda: None)
mark_shutdown = lambda: None
cleanup_resources = lambda: None
"""
    if mode == "cleanup_hung":
        setup += "cleanup_resources = lambda: threading.Event().wait()\n"
    if mode == "worker_hung":
        setup += "threading.Thread(target=lambda: threading.Event().wait()).start()\n"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            setup + functions + "\ngraceful_shutdown(signal.SIGTERM, None)\n",
        ],
        capture_output=True,
        timeout=4,
    )
    assert result.returncode == expected
    assert (b"Shutdown deadline exceeded" in result.stderr) == (expected == 1)
