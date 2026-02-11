from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.utils.camera_discovery import _check_http_endpoint


def _fake_socket(chunks: list[bytes]) -> MagicMock:
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.__exit__.return_value = None
    sock.sendall.return_value = None
    sock.recv.side_effect = chunks + [b""]
    return sock


def test_check_http_endpoint_rejects_html_login_page():
    # Common false positive: /snapshot.jpg returns HTML.
    resp = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html>login</html>"
    with patch("socket.create_connection", return_value=_fake_socket([resp])):
        assert (
            _check_http_endpoint("192.168.2.7", 80, "/snapshot.jpg", timeout=1) is False
        )


def test_check_http_endpoint_accepts_jpeg_magic_without_content_type():
    resp = b"HTTP/1.1 200 OK\r\n\r\n" + b"\xff\xd8\xff" + b"\x00" * 10
    with patch("socket.create_connection", return_value=_fake_socket([resp])):
        assert (
            _check_http_endpoint("192.168.2.123", 80, "/snapshot.jpg", timeout=1)
            is True
        )


def test_check_http_endpoint_accepts_mjpeg_content_type():
    resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        b"\r\n"
        b"--frame\r\n"
    )
    with patch("socket.create_connection", return_value=_fake_socket([resp])):
        assert (
            _check_http_endpoint("192.168.2.123", 80, "/video.mjpg", timeout=1) is True
        )
