"""Fast LAN reachability uses one bounded TCP-attempt budget."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.utils import screenshots as ss


@pytest.fixture
def setup_probe(monkeypatch):
    monkeypatch.setattr(ss, "_get_reachability_cached", lambda *a: None)
    monkeypatch.setattr(ss, "_set_reachability_cached", lambda *a: None)
    monkeypatch.setattr(ss, "get_arp_output", Mock(return_value=b""))
    monkeypatch.setattr(
        ss.psutil,
        "net_if_addrs",
        lambda: {
            "eth0": [SimpleNamespace(family=ss.socket.AF_INET, address="192.168.1.2")]
        },
    )
    clock = [100.0]
    monkeypatch.setattr(ss.time, "monotonic", lambda: clock[0])
    return clock


def test_fast_timeout_is_not_inflated_and_no_arp_process(setup_probe, monkeypatch):
    sock = Mock()
    sock.connect_ex.return_value = 0
    monkeypatch.setattr(ss.socket, "socket", Mock(return_value=sock))
    assert ss.is_address_reachable("192.168.1.9", timeout=0.2)
    assert sock.settimeout.call_args.args[0] == pytest.approx(0.2)
    ss.get_arp_output.assert_not_called()
    sock.close.assert_called_once()


def test_timed_out_first_attempt_does_not_start_more_sockets(setup_probe, monkeypatch):
    sock = Mock()

    def connect(address):
        setup_probe[0] += 0.2
        return 110

    sock.connect_ex.side_effect = connect
    factory = Mock(return_value=sock)
    monkeypatch.setattr(ss.socket, "socket", factory)
    assert not ss.is_address_reachable("192.168.1.9", timeout=0.2)
    factory.assert_called_once()
    sock.close.assert_called_once()


def test_fast_failure_preserves_source_fallback_with_remaining_budget(
    setup_probe, monkeypatch
):
    first, second = Mock(), Mock()

    def connect(address):
        setup_probe[0] += 0.05
        return 111

    first.connect_ex.side_effect = connect
    second.connect_ex.return_value = 0
    monkeypatch.setattr(ss.socket, "socket", Mock(side_effect=[first, second]))
    assert ss.is_address_reachable("192.168.1.9", timeout=0.2)
    assert second.settimeout.call_args.args[0] == pytest.approx(0.15)
    second.bind.assert_called_once_with(("192.168.1.2", 0))
    first.close.assert_called_once()
    second.close.assert_called_once()
