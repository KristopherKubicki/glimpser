from unittest.mock import Mock, patch

import pytest

from app.utils import screenshots


def response_for(chunks, status=200):
    response = Mock(status_code=status)
    response.headers = {}
    response.iter_content.return_value = iter(chunks)
    return response


def probe(response):
    with (
        patch.object(screenshots, "_get_mjpeg_probe", return_value=None),
        patch.object(screenshots, "_set_mjpeg_probe"),
        patch.object(screenshots, "get_preferred_auth", return_value=None),
        patch.object(screenshots, "http_session") as session,
    ):
        session.return_value.get.return_value = response
        return screenshots._probe_mjpeg("http://camera.test/mjpeg")


@pytest.mark.parametrize(
    "chunks", [[b"\xff\xd8frame"], [b"header\xff", b"", b"\xd8frame"]]
)
def test_probe_preserves_first_bytes_and_split_marker(chunks):
    response = response_for(chunks)
    assert probe(response)
    response.iter_content.assert_called_once()
    response.close.assert_called_once()


def test_probe_rejects_http_error_without_reading_body():
    response = response_for([b"\xff\xd8error image"], status=503)
    assert not probe(response)
    response.iter_content.assert_not_called()
    response.close.assert_called_once()


def test_probe_closes_response_if_metadata_access_fails():
    response = response_for([])
    response.headers = None
    response.iter_content.side_effect = RuntimeError("broken response")
    assert not probe(response)
    response.close.assert_called_once()


def test_invalid_stream_has_byte_budget():
    response = response_for([])
    consumed = []

    def endless_junk():
        for _ in range(513):
            consumed.append(1)
            yield b"x" * 2048
        raise AssertionError("read beyond byte budget")

    response.iter_content.return_value = endless_junk()
    assert not screenshots._validate_mjpeg_frame(response)
    assert len(consumed) == 512


def test_probe_checks_elapsed_budget_between_chunks():
    response = response_for([b"junk", b"\xff\xd8late"])
    with patch.object(screenshots.time, "monotonic", side_effect=[0, 1, 6]):
        assert not screenshots._validate_mjpeg_frame(response)


def test_cached_probe_does_not_open_connection():
    with (
        patch.object(screenshots, "_get_mjpeg_probe", return_value=True),
        patch.object(screenshots, "http_session") as session,
    ):
        assert screenshots._probe_mjpeg("http://camera.test/mjpeg")
    session.assert_not_called()
