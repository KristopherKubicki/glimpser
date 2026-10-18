from unittest.mock import Mock

import pytest

from app import routes


class SnapshotResponse:
    """Track response lifetime independently of garbage collection."""

    def __init__(self, status=200, broken=False):
        self.status_code = status
        self.headers = {}
        self.broken = broken
        self.closed = False
        self.reads = 0

    @property
    def content(self):
        self.reads += 1
        if self.broken:
            raise OSError("interrupted body")
        return b"image bytes"

    def close(self):
        self.closed = True


def test_snapshot_releases_response_before_yield(monkeypatch):
    response = SnapshotResponse()
    session = Mock()
    session.get.return_value = response
    monkeypatch.setattr(routes.screenshots, "http_session", lambda: session)
    stream = routes.generate_live_stream("https://example.test/frame.jpg")
    try:
        assert next(stream) == b"image bytes"
        assert response.closed
    finally:
        stream.close()
    session.close.assert_not_called()


@pytest.mark.parametrize("status,broken", [(503, False), (200, True)])
def test_snapshot_failure_releases_socket_before_backoff(monkeypatch, status, broken):
    response = SnapshotResponse(status, broken)
    session = Mock()
    session.get.return_value = response
    monkeypatch.setattr(routes.screenshots, "http_session", lambda: session)

    def sleep(delay):
        assert response.closed
        raise GeneratorExit

    monkeypatch.setattr(routes.time, "sleep", sleep)
    stream = routes.generate_live_stream("https://example.test/frame.jpg")
    with pytest.raises(GeneratorExit):
        next(stream)
    if status != 200:
        assert response.reads == 0, "do not download error bodies to drain a socket"
    session.close.assert_not_called()
