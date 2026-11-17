import importlib.util
import multiprocessing
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

import pytest


def load(root):
    spec = importlib.util.spec_from_file_location(
        "isolated_chrome",
        Path(__file__).resolve().parents[1] / "app" / "utils" / "chrome_utils.py",
    )
    module = importlib.util.module_from_spec(spec)
    app = types.ModuleType("app")
    app.config = types.SimpleNamespace(DANGER_PORT=9222)
    with patch.dict(sys.modules, {"app": app}):
        spec.loader.exec_module(module)
    module._GL_CACHE_PATH = str(root / "cache.sqlite3")
    return module


@pytest.mark.parametrize("supported", [True, False])
def test_workers_share_result(tmp_path, supported):
    binary = tmp_path / "chrome"
    binary.write_text("binary")
    first, second = load(tmp_path), load(tmp_path)
    with patch.object(first, "_probe_browser_gl", return_value=supported) as probe:
        assert first.browser_supports_gl(str(binary)) is supported
        probe.assert_called_once()
    with patch.object(
        second, "_probe_browser_gl", side_effect=AssertionError("reprobe")
    ):
        assert second.browser_supports_gl(str(binary)) is supported


def test_expiry_clock_rollback_and_binary_change(tmp_path):
    binary = tmp_path / "chrome"
    binary.write_text("v1")
    m = load(tmp_path)
    with patch.object(m, "_probe_browser_gl", return_value=True) as probe:
        with patch.object(m.time, "time", return_value=1000):
            assert m.browser_supports_gl(str(binary))
        with patch.object(m.time, "time", return_value=1299):
            assert m.browser_supports_gl(str(binary))
            assert probe.call_count == 1
        with patch.object(m.time, "time", return_value=1300):
            assert m.browser_supports_gl(str(binary))
            assert probe.call_count == 2
        with patch.object(m.time, "time", return_value=999):
            assert m.browser_supports_gl(str(binary))
            assert probe.call_count == 3
            binary.write_text("replacement binary")
            assert m.browser_supports_gl(str(binary))
            assert probe.call_count == 4


def test_unavailable_cache_preserves_probe(tmp_path):
    binary = tmp_path / "chrome"
    binary.write_text("binary")
    m = load(tmp_path)
    m._GL_CACHE_PATH = str(tmp_path)  # A directory cannot be a SQLite file.
    with patch.object(m, "_probe_browser_gl", return_value=True) as probe:
        assert m.browser_supports_gl(str(binary))
        probe.assert_called_once()


def worker(root):
    m = load(root)

    def probe(_):
        with (root / "calls").open("a") as handle:
            handle.write("probe\n")
        time.sleep(0.1)
        return True

    m._probe_browser_gl = probe
    assert m.browser_supports_gl(str(root / "chrome"))


def test_concurrent_processes_probe_once(tmp_path):
    (tmp_path / "chrome").write_text("binary")
    ctx = multiprocessing.get_context("fork")
    processes = [ctx.Process(target=worker, args=(tmp_path,)) for _ in range(6)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    assert (tmp_path / "calls").read_text().splitlines() == ["probe"]


def test_probe_retains_existing_flags_and_timeout(tmp_path):
    m = load(tmp_path)
    with patch.object(m.subprocess, "check_call") as run:
        assert m._probe_browser_gl("/browser") is True
        assert run.call_args.args[0] == [
            "/browser",
            "--headless=new",
            "--use-gl=egl",
            "--dump-dom",
            "about:blank",
        ]
        assert run.call_args.kwargs["timeout"] == 5
    with patch.object(m.subprocess, "check_call", side_effect=OSError):
        assert m._probe_browser_gl("/browser") is False
