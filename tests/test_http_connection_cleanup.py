from unittest.mock import MagicMock, patch

import pytest
import requests

from app.utils import http_probe, screenshots


def test_failed_mp4_inspection_closes_outer_stream():
    response = MagicMock(status_code=200, ok=True)
    response.url = "http://example.test/video.mp4"
    response.headers = {"Content-Type": "video/mp4"}
    with (
        patch.object(http_probe.requests, "get", return_value=response),
        patch.object(
            http_probe, "_probe_mp4_atoms", side_effect=ValueError("bad atom")
        ),
    ):
        ok, info = http_probe.probe_url_with_range(response.url)
        assert ok and info["ok"] and info["status"] == 200
        assert "mp4_probe" not in info
    response.close.assert_called_once()


def test_redirect_limit_is_failure_and_all_streams_are_closed():
    responses = []
    for _ in range(7):
        response = MagicMock(status_code=302, ok=True)
        response.url = "http://example.test/loop"
        response.headers = {"Location": "/loop"}
        responses.append(response)
    with patch.object(http_probe.requests, "get", side_effect=responses) as get:
        assert http_probe.probe_url_with_range("http://example.test/loop") == (
            False,
            {},
        )
    assert get.call_count == 7
    for response in responses:
        response.close.assert_called_once()


@pytest.mark.parametrize(
    "download", [screenshots.download_image, screenshots.download_pdf]
)
def test_authentication_challenge_is_closed_before_retry_even_if_retry_fails(
    tmp_path, download
):
    challenge = MagicMock(status_code=401)
    challenge.headers = {"WWW-Authenticate": 'Digest realm="camera"'}
    session = MagicMock()
    closed_at_retry = []

    def get(*args, **kwargs):
        if session.get.call_count == 1:
            return challenge
        closed_at_retry.append(challenge.close.call_count == 1)
        raise requests.ConnectionError("retry disconnected")

    session.get.side_effect = get
    with (
        patch.object(screenshots, "http_session", return_value=session),
        patch.object(screenshots, "get_cached_status_code", return_value=None),
        patch.object(screenshots, "get_preferred_auth", return_value=object()),
        patch.object(screenshots, "get_digest_auth", return_value=object()),
        patch.object(screenshots, "_set_auth_scheme"),
        patch.object(screenshots, "set_cached_status_code"),
        patch.object(screenshots, "cas_error"),
    ):
        assert (
            download("http://example.test/still", str(tmp_path / "frame.png")) is False
        )
    assert session.get.call_count == 2
    assert closed_at_retry == [True]
    challenge.close.assert_called_once()


@pytest.mark.parametrize("status", [403, 404, 500])
def test_pdf_error_response_closed_without_downloading_body(tmp_path, status):
    response = MagicMock(status_code=status)
    with (
        patch.object(screenshots, "http_session") as session,
        patch.object(screenshots, "get_cached_status_code", return_value=None),
        patch.object(screenshots, "get_preferred_auth", return_value=None),
        patch.object(screenshots, "set_cached_status_code"),
        patch.object(screenshots, "_set_http_error"),
        patch.object(screenshots, "cas_error"),
        patch.object(screenshots, "convert_from_bytes") as convert,
    ):
        session.return_value.get.return_value = response
        assert not screenshots.download_pdf(
            "http://example.test/file.pdf", str(tmp_path / "frame.png")
        )
    response.close.assert_called_once()
    convert.assert_not_called()


def test_pdf_response_closed_before_conversion_even_when_conversion_fails(tmp_path):
    response = MagicMock(status_code=200, content=b"pdf data")
    closed_at_conversion = []

    def convert(*args, **kwargs):
        closed_at_conversion.append(response.close.call_count == 1)
        raise ValueError("invalid pdf")

    with (
        patch.object(screenshots, "http_session") as session,
        patch.object(screenshots, "get_cached_status_code", return_value=None),
        patch.object(screenshots, "get_preferred_auth", return_value=None),
        patch.object(screenshots, "set_cached_status_code"),
        patch.object(screenshots, "cas_error"),
        patch.object(
            screenshots, "convert_from_bytes", side_effect=convert
        ) as conversion,
    ):
        session.return_value.get.return_value = response
        assert not screenshots.download_pdf(
            "http://example.test/file.pdf", str(tmp_path / "frame.png")
        )
    conversion.assert_called_once()
    assert closed_at_conversion == [True]
    response.close.assert_called_once()
