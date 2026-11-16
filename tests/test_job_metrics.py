import ast
import json
import logging
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from threading import Barrier, local
from unittest.mock import Mock

import pytest

try:
    import resource
except ImportError:
    resource = None

SOURCE = Path(__file__).parents[1] / "app/utils/video_archiver.py"


@pytest.fixture
def scope():
    names = {
        "_thread_io_usage",
        "_measure_archive_job",
        "_run_measured_encoder",
        "run_ffmpeg",
    }
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(
        resource=resource,
        os=os,
        time=time,
        logging=logging,
        json=json,
        wraps=wraps,
        _ARCHIVE_JOB_LOCAL=local(),
        run_encoder_command=Mock(
            return_value=subprocess.CompletedProcess([], 0, "", "")
        ),
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def test_result_and_command_preserved(scope, caplog):
    command = ["ffmpeg", "-i", "rtsp://secret@example", "-c:v", "copy", "out.mp4"]
    result = scope["run_encoder_command"].return_value

    def job():
        return scope["_run_measured_encoder"](command, 30)

    with caplog.at_level(logging.INFO):
        assert scope["_measure_archive_job"](job)() is result
    scope["run_encoder_command"].assert_called_once_with(command, timeout=30)
    row = json.loads(caplog.records[-1].args[0])
    assert row["encoder_calls"] == 1
    assert row["encoder_failures"] == 0
    assert "secret" not in caplog.text
    assert scope["_ARCHIVE_JOB_LOCAL"].metrics is None


@pytest.mark.parametrize(
    "exception", [RuntimeError("failed"), subprocess.TimeoutExpired("ffmpeg", 1)]
)
def test_exception_preserved(scope, caplog, exception):
    scope["run_encoder_command"].side_effect = exception

    def job():
        scope["_run_measured_encoder"]([], 1)

    with caplog.at_level(logging.INFO), pytest.raises(type(exception)) as exc:
        scope["_measure_archive_job"](job)()
    assert exc.value is exception
    row = json.loads(caplog.records[-1].args[0])
    assert row["encoder_failures"] == 1 and row["status"] == "error"
    assert scope["_ARCHIVE_JOB_LOCAL"].metrics is None


def test_return_code_failure(scope, caplog):
    scope["run_encoder_command"].return_value = subprocess.CompletedProcess(
        [], 1, "", "bad"
    )

    def job():
        return scope["_run_measured_encoder"]([], 1)

    with caplog.at_level(logging.INFO):
        assert scope["_measure_archive_job"](job)().returncode == 1
    row = json.loads(caplog.records[-1].args[0])
    assert row["encoder_failures"] == 1 and row["status"] == "returned"


def test_concurrent_isolation(scope, caplog):
    barrier = Barrier(2)

    def job(count):
        barrier.wait(timeout=3)
        for _ in range(count):
            scope["_run_measured_encoder"]([], 1)

    measured = scope["_measure_archive_job"](job)
    with caplog.at_level(logging.INFO), ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(measured, [1, 3]))
    assert sorted(json.loads(r.args[0])["encoder_calls"] for r in caplog.records) == [
        1,
        3,
    ]


def test_nested_restore(scope):
    sentinel = {}
    scope["_ARCHIVE_JOB_LOCAL"].metrics = sentinel
    assert scope["_measure_archive_job"](lambda: 12)() == 12
    assert scope["_ARCHIVE_JOB_LOCAL"].metrics is sentinel


@pytest.mark.parametrize(
    "unavailable",
    [
        None,
        object(),
        Mock(RUSAGE_THREAD=1, getrusage=Mock(side_effect=OSError("unsupported"))),
    ],
)
def test_missing_thread_io_preserves_job(scope, caplog, unavailable):
    scope["resource"] = unavailable
    with caplog.at_level(logging.INFO):
        assert scope["_measure_archive_job"](lambda: 42)() == 42
    row = json.loads(caplog.records[-1].args[0])
    assert row["thread_read_blocks"] is None
    assert row["thread_write_blocks"] is None
    assert row["thread_cpu_seconds"] >= 0
    assert scope["_ARCHIVE_JOB_LOCAL"].metrics is None
