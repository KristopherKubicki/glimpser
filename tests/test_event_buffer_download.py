"""Event-buffer downloads bound memory and release pooled HTTP connections."""

from io import BytesIO
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from app.utils import event_buffer as eb


class Response:
    def __init__(self, chunks=(), status=200):
        self.chunks = chunks
        self.status_code = status
        self.closed = False
        self.reads = 0

    @property
    def content(self):
        raise AssertionError("unbounded response.content access")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("source failed")

    def iter_content(self, chunk_size):
        assert chunk_size <= 64 * 1024
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    def close(self):
        self.closed = True


def setup_response(monkeypatch, response):
    get = Mock(return_value=response)
    monkeypatch.setattr(eb._SESSION, "get", get)
    return get


def capture():
    return eb._capture_http_frame("camera", {"url": "http://camera/snapshot"}, 1, 640)


def test_oversized_body_stops_before_reading_rest(monkeypatch):
    response = Response([b"1234", b"5678", b"never-read"])
    get = setup_response(monkeypatch, response)
    monkeypatch.setattr(eb, "_MAX_HTTP_BYTES", 7)
    with pytest.raises(ValueError, match="too large"):
        capture()
    assert response.closed
    assert response.reads == 2
    assert get.call_args.kwargs["stream"] is True


def test_valid_image_closes_socket_before_processing(monkeypatch):
    with BytesIO() as data:
        Image.new("RGB", (2, 2), "red").save(data, "PNG")
        body = data.getvalue()
    response = Response([body[:10], body[10:]])
    setup_response(monkeypatch, response)
    monkeypatch.setattr(eb, "_MAX_HTTP_BYTES", len(body))

    def save(name, image, timestamp, width):
        assert response.closed
        assert image.size == (2, 2)
        image.load()
        return "saved"

    monkeypatch.setattr(eb, "_save_frame", save)
    assert capture() == "saved"


@pytest.mark.parametrize(
    "status,chunks,error", [(503, [], requests.HTTPError), (200, [b"bad"], ValueError)]
)
def test_failed_response_is_closed(monkeypatch, status, chunks, error):
    response = Response(chunks, status)
    setup_response(monkeypatch, response)
    with pytest.raises(error):
        capture()
    assert response.closed


def test_auth_retry_releases_first_response_before_request(monkeypatch):
    first, second = Response(status=401), Response(status=503)
    monkeypatch.setattr(eb, "_template_credentials", lambda _: ("user", "pass"))
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return first
        assert first.closed
        assert isinstance(kwargs["auth"], requests.auth.HTTPDigestAuth)
        return second

    monkeypatch.setattr(eb._SESSION, "get", get)
    with pytest.raises(requests.HTTPError):
        capture()
    assert second.closed
    assert calls[1]["timeout"] <= calls[0]["timeout"]


def test_slow_stream_expires_shared_deadline(monkeypatch):
    response = Response([b"first", b"second"])
    setup_response(monkeypatch, response)
    clock = iter([0, 0, 1, 4])
    monkeypatch.setattr(eb.time, "monotonic", lambda: next(clock))
    with pytest.raises(requests.Timeout, match="deadline"):
        capture()
    assert response.closed


def test_read_failure_closes_response(monkeypatch):
    def chunks():
        yield b"start"
        raise requests.ConnectionError("disconnected")

    response = Response(chunks())
    setup_response(monkeypatch, response)
    with pytest.raises(requests.ConnectionError):
        capture()
    assert response.closed
