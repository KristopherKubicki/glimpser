"""HTTP preflight respects trust boundaries and response ownership."""

from unittest.mock import MagicMock, Mock

import pytest

from app.utils import http_probe as hp


def response(status=200, url="https://source.test/x", headers=None):
    r = MagicMock(status_code=status, url=url, headers=headers or {}, ok=status < 400)
    r.history = []
    return r


@pytest.mark.parametrize(
    "destination",
    ["https://other.test/x", "http://source.test/x", "https://source.test:8443/x"],
)
def test_redirect_does_not_forward_source_credentials(monkeypatch, destination):
    first = response(302, headers={"Location": destination})
    second = response(url=destination)
    get = Mock(side_effect=[first, second])
    monkeypatch.setattr(hp.requests, "get", get)
    headers = {
        "Authorization": "secret",
        "Cookie": "session=secret",
        "Range": "bytes=0-1",
    }
    hp._get_with_redirects(
        first.url,
        {"timeout": 3, "headers": headers, "auth": ("u", "p"), "stream": True},
    )
    kwargs = get.call_args.kwargs
    assert kwargs.get("auth") is None
    assert "Authorization" not in kwargs["headers"]
    assert "Cookie" not in kwargs["headers"]
    assert kwargs["headers"]["Range"] == "bytes=0-1"
    assert headers["Authorization"] == "secret"
    first.close.assert_called_once()


def test_same_origin_redirect_preserves_auth(monkeypatch):
    first = response(302, headers={"Location": "/next"})
    get = Mock(side_effect=[first, response(url="https://source.test/next")])
    monkeypatch.setattr(hp.requests, "get", get)
    hp._get_with_redirects(
        first.url,
        {"timeout": 3, "headers": {"Authorization": "secret"}, "auth": ("u", "p")},
    )
    assert get.call_args.kwargs["auth"] == ("u", "p")


def test_error_etag_not_reused_as_success_validator(monkeypatch):
    hp.clear_probe_cache()
    get = Mock(side_effect=[response(503, headers={"ETag": "error"}), response()])
    monkeypatch.setattr(hp.requests, "get", get)
    for _ in range(2):
        hp.probe_url_with_range(
            "https://source.test/x", range_header="", probe_mp4_atoms=False
        )
    assert "If-None-Match" not in get.call_args.kwargs["headers"]
    hp.clear_probe_cache()


def test_metadata_fetch_releases_first_response_and_failure_keeps_http_evidence(
    monkeypatch,
):
    r = response(headers={"Content-Type": "video/mp4"})
    monkeypatch.setattr(hp.requests, "get", Mock(return_value=r))

    def metadata(**kwargs):
        r.close.assert_called_once()
        raise hp.requests.ConnectionError("optional metadata interrupted")

    monkeypatch.setattr(hp, "_probe_mp4_atoms", metadata)
    ok, info = hp.probe_url_with_range(r.url, use_conditional_cache=False)
    assert ok and info["ok"] and info["status"] == 200


def test_preconnect_respects_verification_disabled(monkeypatch):
    monkeypatch.setattr(
        hp.socket,
        "getaddrinfo",
        Mock(
            return_value=[
                (hp.socket.AF_INET, hp.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
            ]
        ),
    )
    monkeypatch.setattr(hp.socket, "socket", MagicMock())
    context = MagicMock()
    monkeypatch.setattr(hp.ssl, "create_default_context", Mock(return_value=context))
    monkeypatch.setattr(hp.requests, "get", Mock(return_value=response()))
    ok, _ = hp.probe_url_with_range(
        "https://source.test/x", preconnect=True, verify=False, probe_mp4_atoms=False
    )
    assert ok
    assert context.check_hostname is False
    assert context.verify_mode == hp.ssl.CERT_NONE


def test_malformed_redirect_closes_response(monkeypatch):
    first = response(302, headers={"Location": "https://target.test:bad/x"})
    monkeypatch.setattr(hp.requests, "get", Mock(return_value=first))
    with pytest.raises(ValueError):
        hp._get_with_redirects(first.url, {"timeout": 3})
    first.close.assert_called_once()


def test_preconnect_shares_overall_probe_budget(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(hp.time, "monotonic", lambda: clock[0])

    def preconnect(*args, **kwargs):
        assert kwargs["timeout"] == 2
        clock[0] = 2
        return True, "ok"

    monkeypatch.setattr(hp, "_preconnect_check", preconnect)
    get = Mock(return_value=response())
    monkeypatch.setattr(hp.requests, "get", get)
    assert hp.probe_url_with_range(
        "https://source.test/x", timeout=3, preconnect=True, probe_mp4_atoms=False
    )[0]
    assert get.call_args.kwargs["timeout"] == 1


@pytest.mark.parametrize("verify", [True, "/test/ca.pem"])
def test_preconnect_preserves_certificate_verification(monkeypatch, verify):
    monkeypatch.setattr(
        hp.socket,
        "getaddrinfo",
        Mock(
            return_value=[
                (hp.socket.AF_INET, hp.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
            ]
        ),
    )
    monkeypatch.setattr(hp.socket, "socket", MagicMock())
    context = MagicMock()
    factory = Mock(return_value=context)
    monkeypatch.setattr(hp.ssl, "create_default_context", factory)
    assert hp._preconnect_check("https://source.test", verify=verify)[0]
    if isinstance(verify, str):
        factory.assert_called_once_with(cafile=verify)
    else:
        factory.assert_called_once_with()
    assert context.check_hostname is not False
    assert context.verify_mode != hp.ssl.CERT_NONE


def test_preconnect_supports_ca_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(
        hp.socket,
        "getaddrinfo",
        Mock(
            return_value=[
                (hp.socket.AF_INET, hp.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
            ]
        ),
    )
    monkeypatch.setattr(hp.socket, "socket", MagicMock())
    factory = Mock(return_value=MagicMock())
    monkeypatch.setattr(hp.ssl, "create_default_context", factory)
    assert hp._preconnect_check("https://source.test", verify=str(tmp_path))[0]
    factory.assert_called_once_with(capath=str(tmp_path))


def test_sparse_range_rejects_encoded_offsets_and_closes(monkeypatch):
    r = response(
        206,
        headers={
            "Content-Type": "multipart/byteranges; boundary=x",
            "Content-Encoding": "gzip",
        },
    )
    get = Mock(return_value=r)
    monkeypatch.setattr(hp.requests, "get", get)
    assert (
        hp._fetch_sparse_multi_ranges(
            r.url,
            timeout=3,
            allow_redirects=True,
            headers={},
            auth=None,
            verify=True,
            range_header="bytes=0-1,4-5",
        )
        == {}
    )
    assert get.call_args.kwargs["headers"]["Accept-Encoding"] == "identity"
    r.iter_content.assert_not_called()
    r.close.assert_called_once()


def test_rtsps_preconnect_uses_secure_port_and_tls(monkeypatch):
    dns = Mock(
        return_value=[
            (hp.socket.AF_INET, hp.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ]
    )
    monkeypatch.setattr(hp.socket, "getaddrinfo", dns)
    monkeypatch.setattr(hp.socket, "socket", MagicMock())
    context = MagicMock()
    monkeypatch.setattr(hp.ssl, "create_default_context", Mock(return_value=context))
    assert hp._preconnect_check("rtsps://source.test/live")[0]
    assert dns.call_args.args == ("source.test", 322)
    context.wrap_socket.assert_called_once()
