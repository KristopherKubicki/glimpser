from unittest.mock import Mock, patch

import pytest

from app.utils import http_probe


def fetch(response, requested="bytes=100-103"):
    with patch.object(http_probe.requests, "get", return_value=response) as get:
        result = http_probe._fetch_range_chunk(
            "http://camera.test/video.mp4",
            timeout=3,
            allow_redirects=True,
            headers={},
            auth=None,
            verify=True,
            range_header=requested,
        )
    return result, get


def response(status=206, content_range="bytes 100-103/200", body=b"tail"):
    result = Mock(status_code=status)
    result.headers = {"Content-Range": content_range}
    result.iter_content.return_value = iter([body])
    return result


def test_ignored_tail_range_is_closed_without_reading_body():
    r = response(status=200, body=b"head")
    result, _ = fetch(r)
    assert result == b""
    r.iter_content.assert_not_called()
    r.close.assert_called_once()


def test_ignored_prefix_range_can_still_supply_a_bounded_prefix():
    r = response(status=200, body=b"head" * 100)
    result, _ = fetch(r, "bytes=0-3")
    assert result == b"head"
    r.close.assert_called_once()


@pytest.mark.parametrize(
    "header",
    [
        "",
        "bytes 0-3/200",
        "bytes 100-104/200",
        "bytes 100-103/102",
        "bytes 103-100/200",
    ],
)
def test_bad_content_range_is_rejected_before_body_read(header):
    r = response(content_range=header)
    result, _ = fetch(r)
    assert result == b""
    r.iter_content.assert_not_called()
    r.close.assert_called_once()


def test_complete_valid_tail_is_preserved():
    r = response()
    result, get = fetch(r)
    assert result == b"tail"
    assert get.call_args.kwargs["headers"]["Accept-Encoding"] == "identity"
    r.close.assert_called_once()


def test_short_valid_range_at_eof_is_accepted():
    r = response(content_range="bytes 100-101/102", body=b"ok")
    assert fetch(r)[0] == b"ok"


def test_truncated_partial_response_is_rejected():
    r = response(body=b"ta")
    assert fetch(r)[0] == b""
    r.close.assert_called_once()


def test_unexpected_compression_is_not_interpreted_as_byte_offsets():
    r = response()
    r.headers["Content-Encoding"] = "gzip"
    assert fetch(r)[0] == b""
    r.iter_content.assert_not_called()
    r.close.assert_called_once()


def test_invalid_request_does_not_start_unbounded_download():
    r = response()
    result, get = fetch(r, "bytes=100-")
    assert result == b""
    get.assert_not_called()


def test_sparse_tail_only_is_not_mistaken_for_front():
    with (
        patch.object(
            http_probe,
            "_fetch_sparse_multi_ranges",
            return_value={368928: b"\x00\x00\x00\x08moov"},
        ),
        patch.object(
            http_probe, "_fetch_range_chunk", return_value=b"\x00\x00\x00\x08ftyp"
        ) as front,
    ):
        info = http_probe._probe_mp4_atoms(
            url="http://camera.test/video.mp4",
            effective_url="http://camera.test/video.mp4",
            content_type="video/mp4",
            content_range="bytes 0-1/500000",
            timeout=3,
            allow_redirects=True,
            headers={},
            auth=None,
            verify=True,
        )
    assert info["ftyp"] is True
    assert info["moov"] == "tail"
    assert info["moov_offset"] == 368928
    front.assert_called_once()
    assert front.call_args.kwargs["range_header"] == "bytes=0-131071"
