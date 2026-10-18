"""Preconnect resolves once and shares its budget across address candidates."""

import socket
from unittest.mock import MagicMock, Mock

import pytest
import pytest_socket

from app.utils import http_probe as hp

ADDRESSES = [
    (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 80, 0, 0)),
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
]


def test_preconnect_reuses_dns_and_remaining_budget(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(hp.time, "monotonic", lambda: clock[0])
    dns = Mock(return_value=ADDRESSES)
    monkeypatch.setattr(hp.socket, "getaddrinfo", dns)
    first, second = MagicMock(), MagicMock()

    def fail(address):
        clock[0] += 1.25
        raise OSError("unreachable IPv6")

    first.connect.side_effect = fail
    factory = Mock(side_effect=[first, second])
    monkeypatch.setattr(hp.socket, "socket", factory)
    assert hp._preconnect_check("http://source.test", timeout=2) == (True, "ok")
    dns.assert_called_once()
    first.settimeout.assert_called_once_with(2)
    second.settimeout.assert_called_once_with(0.75)
    first.connect.assert_called_once_with(ADDRESSES[0][4])
    second.connect.assert_called_once_with(ADDRESSES[1][4])
    first.close.assert_called_once()
    second.__exit__.assert_called_once()


def test_exhausted_budget_does_not_open_next_socket(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(hp.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(hp.socket, "getaddrinfo", Mock(return_value=ADDRESSES))
    sock = MagicMock()

    def fail(address):
        clock[0] = 2
        raise TimeoutError()

    sock.connect.side_effect = fail
    factory = Mock(return_value=sock)
    monkeypatch.setattr(hp.socket, "socket", factory)
    assert hp._preconnect_check("http://source.test", timeout=2) == (
        False,
        "tcp_failed",
    )
    factory.assert_called_once()
    sock.close.assert_called_once()


@pytest.fixture
def loopback_sockets():
    pytest_socket.enable_socket()
    try:
        yield
    finally:
        pytest_socket.disable_socket()


def test_real_loopback_closes_connected_socket(monkeypatch, loopback_sockets):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        address = listener.getsockname()
        monkeypatch.setattr(
            hp.socket,
            "getaddrinfo",
            Mock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", address)]),
        )
        assert hp._preconnect_check("http://source.test", timeout=1) == (True, "ok")
        listener.settimeout(1)
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(1)
            assert conn.recv(1) == b""


@pytest.mark.parametrize(
    "error", [OSError("connection refused"), RuntimeError("interrupted setup")]
)
def test_failed_setup_closes_socket(monkeypatch, error):
    sock = MagicMock()
    sock.settimeout.side_effect = error
    monkeypatch.setattr(hp.socket, "socket", Mock(return_value=sock))
    with pytest.raises(type(error)):
        hp._connect_resolved(ADDRESSES[:1], 2, hp.time.monotonic() + 2)
    sock.close.assert_called_once()
