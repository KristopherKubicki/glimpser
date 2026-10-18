"""Scheduler bursts should not repeat TLS probes or retain failed connectivity."""

from unittest.mock import Mock

import pytest

from app.utils import network_probe_cache as cache


@pytest.fixture
def probe(monkeypatch):
    clock = [100.0]
    check = Mock(return_value=True)
    monkeypatch.setattr(cache, "_success", None)
    monkeypatch.setattr(cache.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(cache.network, "is_system_online", check)
    return check, clock


def test_burst_reuses_success_but_probes_again_at_expiry(probe):
    check, clock = probe
    for _ in range(100):
        assert cache.cached_is_system_online()
    assert check.call_count == 1
    clock[0] += 5
    check.return_value = False
    assert not cache.cached_is_system_online()
    assert check.call_count == 2


def test_offline_result_does_not_delay_recovery(probe):
    check, _ = probe
    check.return_value = False
    assert not cache.cached_is_system_online()
    check.return_value = True
    assert cache.cached_is_system_online()
    assert check.call_count == 2


@pytest.mark.parametrize("setting", cache._PROBE_SETTINGS)
def test_changed_probe_configuration_invalidates_immediately(
    probe, monkeypatch, setting
):
    check, _ = probe
    assert cache.cached_is_system_online()
    monkeypatch.setenv(setting, "changed-value")
    assert cache.cached_is_system_online()
    assert check.call_count == 2


def test_forked_worker_rechecks_inherited_success(probe, monkeypatch):
    check, _ = probe
    monkeypatch.setattr(cache.os, "getpid", lambda: 100)
    assert cache.cached_is_system_online()
    monkeypatch.setattr(cache.os, "getpid", lambda: 101)
    assert cache.cached_is_system_online()
    assert check.call_count == 2


def test_changed_timeout_is_not_hidden_by_cache(probe):
    check, _ = probe
    assert cache.cached_is_system_online(timeout=1)
    assert cache.cached_is_system_online(timeout=3)
    assert check.call_count == 2
