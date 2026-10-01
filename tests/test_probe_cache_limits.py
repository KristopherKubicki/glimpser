"""Bound validator storage and never reuse superseded metadata."""

import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, Mock

import pytest

from app.utils import http_probe as hp


@pytest.fixture(autouse=True)
def empty_cache():
    hp.clear_probe_cache()
    yield
    hp.clear_probe_cache()


def test_rotating_urls_are_bounded(monkeypatch):
    monkeypatch.setattr(hp, "PROBE_CACHE_MAX_ENTRIES", 8, raising=False)
    for i in range(100):
        hp._cache_set(str(i), etag=str(i))
    assert len(hp._probe_conditional_cache) <= 8
    assert hp._cache_get("0") is None
    assert hp._cache_get("99")["etag"] == "99"


def test_expiry_ignores_wall_clock_reversal(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(hp.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(hp.time, "time", lambda: 1000 - clock[0])
    hp._cache_set("url", etag="old")
    clock[0] = hp.PROBE_CACHE_TTL_SECONDS + 1
    assert hp._cache_get("url") is None


def test_new_writes_sweep_expired_urls(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(hp.time, "monotonic", lambda: clock[0])
    hp._cache_set("old", etag="old")
    clock[0] += hp.PROBE_CACHE_TTL_SECONDS + 1
    hp._cache_set("new", etag="new")
    assert "old" not in hp._probe_conditional_cache


def test_success_without_validator_invalidates_previous_value(monkeypatch):
    url = "http://source.test/media"
    hp._cache_set(url, etag="old")
    r = MagicMock(status_code=200, ok=True, url=url, headers={})
    r.history = []
    get = Mock(return_value=r)
    monkeypatch.setattr(hp.requests, "get", get)
    for _ in range(2):
        assert hp.probe_url_with_range(url, probe_mp4_atoms=False)[0]
    assert "If-None-Match" not in get.call_args.kwargs["headers"]


def test_large_entry_is_not_retained(monkeypatch):
    monkeypatch.setattr(hp, "PROBE_CACHE_MAX_ENTRY_CHARS", 32, raising=False)
    hp._cache_set("url", etag="small")
    hp._cache_set("url", etag="x" * 33)
    assert hp._cache_get("url") is None


def test_concurrent_updates_reads_and_clears_stay_bounded(monkeypatch):
    monkeypatch.setattr(hp, "PROBE_CACHE_MAX_ENTRIES", 8, raising=False)

    def exercise(worker):
        for i in range(200):
            url = f"{worker}-{i}"
            hp._cache_set(url, etag=str(i))
            hp._cache_get(url)
            if i % 17 == 0:
                hp.clear_probe_cache()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(exercise, range(4)))
    assert len(hp._probe_conditional_cache) <= 8


def _child_cache_check(connection):
    hp._cache_set("child", etag="child")
    connection.send(hp._cache_get("child")["etag"])
    connection.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires fork")
def test_fork_child_does_not_inherit_locked_cache():
    ctx = multiprocessing.get_context("fork")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child_cache_check, args=(child,))
    try:
        with hp._probe_cache_lock:
            process.start()
            child.close()
            assert parent.poll(5), "child blocked on inherited cache lock"
            assert parent.recv() == "child"
        process.join(5)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        parent.close()
        child.close()
