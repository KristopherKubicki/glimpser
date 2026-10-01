"""Connectivity targets preserve IPv6 and isolate malformed fallback entries."""

from unittest.mock import Mock

import pytest

from app.utils import network as net


@pytest.mark.parametrize(
    "target,expected",
    [
        ("::1", ("::1", 443)),
        ("2001:db8::1234", ("2001:db8::1234", 443)),
        ("[::1]", ("::1", 443)),
        ("[::1]:8443", ("::1", 8443)),
        ("[fe80::1%eth0]:80", ("fe80::1%eth0", 80)),
        ("camera.local:8080", ("camera.local", 8080)),
        ("192.0.2.1", ("192.0.2.1", 443)),
    ],
)
def test_parses_target_without_damaging_address(target, expected):
    assert net._parse_target(target, 443) == expected


@pytest.mark.parametrize(
    "target",
    ["camera:65536", "camera:-1", "camera:bad", "[::1", "[::1]oops", ":80", ""],
)
def test_invalid_target_does_not_open_socket(monkeypatch, target):
    connect = Mock(side_effect=AssertionError("invalid socket target"))
    monkeypatch.setattr(net.socket, "create_connection", connect)
    assert not net._try_connect(target, 1, 443)
    connect.assert_not_called()


def test_invalid_first_target_does_not_hide_healthy_fallback(monkeypatch):
    monkeypatch.setenv("ONLINE_TEST_URLS", "")
    monkeypatch.setenv("ONLINE_TEST_HOSTS", "bad:99999,[::1]:443")
    monkeypatch.setenv("ONLINE_TEST_PORT", "443")
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)

    def connect(address, timeout):
        if address[1] > 65535:
            raise OverflowError("port out of range")
        assert address == ("::1", 443)
        return connection

    monkeypatch.setattr(net.socket, "create_connection", connect)
    assert net.is_system_online(timeout=1)
    connection.__exit__.assert_called_once()
