"""LAN admission probes the configured service, not another port on its host."""

from unittest.mock import Mock

import pytest

from app.utils import screenshots as ss


@pytest.mark.parametrize(
    "url,port",
    [
        ("http://192.168.1.9:8080/frame", 8080),
        ("https://192.168.1.9:8443/frame", 8443),
        ("rtsp://192.168.1.9:8554/stream", 8554),
        ("rtsps://192.168.1.9:8322/stream", 8322),
        ("http://192.168.1.9/frame", 80),
        ("https://192.168.1.9/frame", 443),
        ("rtsp://192.168.1.9/stream", 554),
        ("rtsps://192.168.1.9/stream", 322),
    ],
)
def test_failed_endpoint_is_probed_once_on_its_own_port(monkeypatch, url, port):
    monkeypatch.setattr(ss, "_get_auth_hint", lambda _: False)
    monkeypatch.setattr(ss, "_local_quarantine_active", lambda _: (False, 0))
    monkeypatch.setattr(ss, "network_state", lambda: {"lan_ok": True})
    monkeypatch.setattr(ss, "_is_lan_target", lambda _: True)
    monkeypatch.setattr(ss, "_record_tier_failure", Mock())
    backoff = Mock()
    monkeypatch.setattr(ss, "record_preflight_backoff", backoff)
    probe = Mock(return_value=False)
    monkeypatch.setattr(ss, "is_address_reachable", probe)
    assert ss._capture_or_download_inner("camera", {}, url, url, None, None) is False
    probe.assert_called_once_with(
        "192.168.1.9",
        port=port,
        timeout=max(0.2, float(ss.PREFLIGHT_LAN_FAST_PROBE_TIMEOUT)),
    )
    assert backoff.call_args.args[1] == "local_unreachable_fast"
