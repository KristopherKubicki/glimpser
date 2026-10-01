from unittest.mock import Mock, patch

import pytest
import requests

from app.utils import http_probe, screenshots


@pytest.mark.parametrize("verify", [True, False])
@pytest.mark.parametrize("port", [None, 7441])
def test_rtsps_wraps_before_sending_and_preserves_certificate_policy(verify, port):
    raw, secured, context = Mock(), Mock(), Mock()
    context.wrap_socket.return_value = secured
    secured.recv.return_value = b"RTSP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n"
    url = "rtsps://camera.test" + (f":{port}" if port else "") + "/stream"
    with (
        patch.object(
            screenshots.socket, "create_connection", return_value=raw
        ) as connect,
        patch.object(screenshots.ssl, "create_default_context", return_value=context),
        patch.object(screenshots.config, "REQUEST_VERIFY_SSL", verify),
    ):
        assert screenshots._rtsp_request(url, "OPTIONS", 3)[0] == 200
    connect.assert_called_once_with(("camera.test", port or 322), timeout=3)
    context.wrap_socket.assert_called_once_with(
        raw, server_hostname="camera.test", do_handshake_on_connect=False
    )
    secured.do_handshake.assert_called_once()
    raw.sendall.assert_not_called()
    secured.close.assert_called_once()
    if not verify:
        assert context.check_hostname is False
        assert context.verify_mode == screenshots.ssl.CERT_NONE
    else:
        assert "verify_mode" not in context.__dict__
        assert "check_hostname" not in context.__dict__


def test_tls_failure_closes_connection_without_plaintext_fallback():
    raw, secured, context = Mock(), Mock(), Mock()
    context.wrap_socket.return_value = secured
    secured.do_handshake.side_effect = screenshots.ssl.SSLError("bad certificate")
    with (
        patch.object(screenshots.socket, "create_connection", return_value=raw),
        patch.object(screenshots.ssl, "create_default_context", return_value=context),
    ):
        assert screenshots._rtsp_request(
            "rtsps://camera.test/stream", "OPTIONS", 3
        ) == (0, "", {})
    raw.sendall.assert_not_called()
    secured.sendall.assert_not_called()
    secured.close.assert_called_once()


def test_plain_and_secure_probe_caches_cannot_collide_on_same_port():
    assert (
        screenshots._rtsp_key("rtsps://camera.test/stream") == "rtsps://camera.test:322"
    )
    assert screenshots._rtsp_key(
        "rtsp://camera.test:322/stream"
    ) != screenshots._rtsp_key("rtsps://camera.test:322/stream")


def response(status, headers=None):
    r = Mock(status_code=status, ok=status < 400)
    r.headers = headers or {}
    r.url = "http://camera.test/"
    r.history = []
    return r


def test_redirects_consume_one_budget_and_close_previous_response():
    redirect = response(302, {"Location": "/next"})
    end = response(200)
    with (
        patch.object(http_probe.time, "monotonic", side_effect=[1, 2]),
        patch.object(http_probe.requests, "get", side_effect=[redirect, end]) as get,
    ):
        assert (
            http_probe._get_with_redirects(
                "http://camera.test/", {"timeout": 3}, deadline=3
            )[0]
            is end
        )
    assert [c.kwargs["timeout"] for c in get.call_args_list] == [2, 1]
    redirect.close.assert_called_once()


def test_exhausted_redirect_budget_stops_before_next_request():
    redirect = response(302, {"Location": "/next"})
    with (
        patch.object(http_probe.time, "monotonic", side_effect=[1, 4]),
        patch.object(http_probe.requests, "get", return_value=redirect) as get,
    ):
        with pytest.raises(requests.Timeout):
            http_probe._get_with_redirects(
                "http://camera.test/", {"timeout": 3}, deadline=3
            )
    get.assert_called_once()
    redirect.close.assert_called_once()


def test_fallback_retry_uses_remaining_budget():
    first = response(416)
    second = response(200)
    with (
        patch.object(http_probe.time, "monotonic", side_effect=[0, 1, 2]),
        patch.object(http_probe.requests, "get", side_effect=[first, second]) as get,
    ):
        ok, _ = http_probe.probe_url_with_range(
            "http://camera.test/",
            timeout=3,
            allow_redirects=False,
            use_conditional_cache=False,
            probe_mp4_atoms=False,
        )
    assert ok
    assert [c.kwargs["timeout"] for c in get.call_args_list] == [2, 1]
    second.close.assert_called_once()


def test_optional_media_budget_exhaustion_preserves_http_success():
    r = response(200, {"Content-Type": "video/mp4"})
    with (
        patch.object(http_probe.time, "monotonic", side_effect=[0, 1, 4]),
        patch.object(http_probe.requests, "get", return_value=r) as get,
    ):
        ok, info = http_probe.probe_url_with_range(
            "http://camera.test/video.mp4",
            timeout=3,
            allow_redirects=False,
            use_conditional_cache=False,
        )
    assert ok and info["status"] == 200
    get.assert_called_once()
    r.close.assert_called_once()
