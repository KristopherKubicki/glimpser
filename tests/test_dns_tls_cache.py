"""DNS cache hits must not bypass TLS; failed probes have short recovery TTLs."""

from unittest.mock import MagicMock, Mock

import pytest

from app.utils import screenshots as ss


@pytest.fixture
def probes(monkeypatch):
    for name in ("dns_cache", "dns_cache_time", "tls_cache", "tls_cache_time"):
        monkeypatch.setattr(ss, name, {})
    monkeypatch.setattr(ss.time, "time", lambda: 1000.0)
    monkeypatch.setattr(ss, "_persist_preflight_cache", lambda: None)
    monkeypatch.setattr(ss.config, "REQUEST_VERIFY_SSL", True)
    dns = Mock(return_value=[])
    connect = Mock(side_effect=OSError("TLS unavailable"))
    monkeypatch.setattr(ss.socket, "getaddrinfo", dns)
    monkeypatch.setattr(ss.socket, "create_connection", connect)
    return dns, connect


def test_cached_dns_does_not_bypass_failed_tls(probes):
    dns, connect = probes
    for _ in range(2):
        assert ss._preflight_dns_tls("https://camera.example")[0] is False
    assert dns.call_count == 1
    assert connect.call_count == 1


def test_failed_dns_is_cached_briefly_then_retried(probes, monkeypatch):
    dns, connect = probes
    dns.side_effect = OSError("DNS unavailable")
    for _ in range(2):
        assert ss._preflight_dns_tls("https://camera.example") == (False, "dns_failed")
    assert dns.call_count == 1
    monkeypatch.setattr(ss.time, "time", lambda: 1031.0)
    dns.side_effect = None
    assert not ss._preflight_dns_tls("https://camera.example")[0]
    assert dns.call_count == 2
    assert connect.call_count == 1


def test_tls_failure_expires_independently_of_dns(probes, monkeypatch):
    dns, connect = probes
    assert not ss._preflight_dns_tls("https://camera.example")[0]
    monkeypatch.setattr(ss.time, "time", lambda: 1031.0)
    connect.side_effect = None
    connect.return_value = MagicMock()
    context = MagicMock()
    context.wrap_socket.return_value.__enter__.return_value.selected_alpn_protocol.return_value = (
        None
    )
    monkeypatch.setattr(ss.ssl, "create_default_context", lambda: context)
    assert ss._preflight_dns_tls("https://camera.example") == (True, "tls_ok")
    assert dns.call_count == 1
    assert connect.call_count == 2
    assert ss._preflight_dns_tls("https://camera.example") == (True, "tls_cache")
    assert connect.call_count == 2


def test_dns_hit_still_checks_new_https_target(probes):
    dns, connect = probes
    assert ss._preflight_dns_tls("http://camera.example:443")[0]
    assert not ss._preflight_dns_tls("https://camera.example:443")[0]
    assert dns.call_count == 1
    connect.assert_called_once()


def test_verification_disabled_still_skips_tls(probes, monkeypatch):
    _, connect = probes
    monkeypatch.setattr(ss.config, "REQUEST_VERIFY_SSL", False)
    assert ss._preflight_dns_tls("https://camera.example")[0]
    assert ss._preflight_dns_tls("https://camera.example")[0]
    connect.assert_not_called()
