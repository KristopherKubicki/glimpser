import concurrent.futures
import importlib.util
import json
import multiprocessing
from pathlib import Path
from unittest.mock import patch

import pytest


def load(path):
    spec = importlib.util.spec_from_file_location(
        "isolated_profiling",
        Path(__file__).resolve().parents[1] / "app" / "utils" / "profiling.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.LOG_PATH = str(path)
    return module


def test_legacy_and_new_stats(tmp_path):
    path = tmp_path / "latency.json"
    original = json.dumps(
        [{"route": "a", "elapsed_ms": 10}, {"route": "a", "elapsed_ms": 20}]
    )
    path.write_text(original)
    m = load(path)
    m._append_entry({"route": "a", "elapsed_ms": 30})
    m._append_entry({"route": "b", "elapsed_ms": 5})
    assert m.get_latency_stats() == {
        "a": {"count": 3, "average_ms": 20},
        "b": {"count": 1, "average_ms": 5},
    }
    assert path.read_text() == original


def test_no_history_read_on_request(tmp_path):
    m = load(tmp_path / "log.json")
    with (
        patch.object(m, "_load_log", side_effect=AssertionError("history read")),
        patch.object(m.time, "time", side_effect=[10, 10.025, 11]),
    ):
        assert m.profile_route("test")(lambda value: value)(42) == 42
    stats = m.get_latency_stats()["test"]
    assert stats["count"] == 1
    assert stats["average_ms"] == pytest.approx(25)


def test_fresh_stats_and_partial_record(tmp_path):
    m = load(tmp_path / "log.json")
    assert m.get_latency_stats() == {}
    Path(m.LOG_PATH + ".jsonl").write_text('{"route": "partial"')
    m._append_entry({"route": "next", "elapsed_ms": 2})
    assert m.get_latency_stats() == {"next": {"count": 1, "average_ms": 2}}


def test_storage_failure_preserves_response_and_exception(tmp_path):
    m = load(tmp_path / "log.json")
    with patch.object(m, "_append_entry", side_effect=OSError("full")):
        assert m.profile_route()(lambda: "ok")() == "ok"

        @m.profile_route()
        def fail():
            raise ValueError("original")

        with pytest.raises(ValueError, match="original"):
            fail()


def test_exception_is_profiled(tmp_path):
    m = load(tmp_path / "log.json")

    @m.profile_route("error")
    def fail():
        raise LookupError()

    with pytest.raises(LookupError):
        fail()
    assert m.get_latency_stats()["error"]["count"] == 1


def append_worker(path):
    m = load(path)
    for _ in range(40):
        m.profile_route("worker")(lambda: None)()


def test_threads_and_processes(tmp_path):
    path = tmp_path / "log.json"
    m = load(path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: m.profile_route("thread")(lambda: None)(), range(80)))
    context = multiprocessing.get_context("fork")
    processes = [context.Process(target=append_worker, args=(path,)) for _ in range(4)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    assert m.get_latency_stats()["worker"]["count"] == 160
    assert m.get_latency_stats()["thread"]["count"] == 80


def test_corrupt_legacy_does_not_hide_new_records(tmp_path):
    path = tmp_path / "log.json"
    path.write_text("broken")
    m = load(path)
    m._append_entry({"route": "new", "elapsed_ms": 1})
    assert m.get_latency_stats() == {"new": {"count": 1, "average_ms": 1}}
