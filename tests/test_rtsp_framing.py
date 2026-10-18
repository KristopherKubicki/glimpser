from unittest.mock import Mock, patch

import pytest

from app.utils import screenshots


def request(chunks, url="rtsp://camera.test/stream"):
    sock = Mock()
    sock.recv.side_effect = chunks
    with patch.object(screenshots.socket, "create_connection", return_value=sock):
        result = screenshots._rtsp_request(url, "DESCRIBE", 3)
    sock.close.assert_called_once()
    return result, sock


def test_response_survives_every_byte_being_a_separate_read():
    body = b"v=0\r\na=rtpmap:96 H264/90000\r\n"
    wire = (
        b"RTSP/1.0 200 OK\r\ncontent-type: application/sdp\r\ncontent-length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    (status, response, headers), sock = request([bytes([b]) for b in wire])
    assert status == 200
    assert response.endswith(body.decode())
    assert headers["Content-Type"] == "application/sdp"
    assert "a=rtpmap" not in headers
    assert sock.recv.call_count == len(wire)


def test_authentication_drains_challenge_body_before_second_response():
    challenge = b'RTSP/1.0 401 Unauthorized\r\nwww-authenticate: Basic realm="camera"\r\nContent-Length: 4\r\n\r\n'
    (status, _, _), sock = request(
        [challenge, b"no", b"pe", b"RTSP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n"],
        "rtsp://user:password@camera.test/stream",
    )
    assert status == 200
    assert sock.sendall.call_count == 2
    assert b"Authorization: Basic " in sock.sendall.call_args.args[0]


@pytest.mark.parametrize(
    "wire",
    [
        b"RTSP/1.0 200 OK\r\nContent-Length: 10\r\n\r\nshort",
        b"RTSP/1.0 200 OK\r\nContent-Length: -1\r\n\r\n",
        b"RTSP/1.0 200 OK\r\nContent-Length: 1048577\r\n\r\n",
        b"RTSP/1.0 200 OK\r\nContent-Length: 0\r\ncontent-length: 1\r\n\r\n",
        b"RTSP/1.0 200 OK\r\nUnfinished: value",
    ],
)
def test_invalid_or_truncated_response_fails_closed(wire):
    result, _ = request([wire, b""])
    assert result == (0, "", {})


def test_header_budget_bounds_continuous_input():
    result, sock = request([b"x" * 4096] * 16)
    assert result == (0, "", {})
    assert sock.recv.call_count == 16


def test_fragmented_response_cannot_reset_deadline():
    with patch.object(screenshots.time, "monotonic", side_effect=[0, 1, 4]):
        result, sock = request([b"RTSP/1.0 "])
    assert result == (0, "", {})
    assert sock.recv.call_count == 1


def test_authentication_shares_original_deadline():
    with patch.object(screenshots.time, "monotonic", side_effect=[0, 1, 4]):
        result, sock = request(
            [b"RTSP/1.0 401 Unauthorized\r\nWWW-Authenticate: Basic\r\n\r\n"],
            "rtsp://user:password@camera.test/stream",
        )
    assert result == (0, "", {})
    assert sock.sendall.call_count == 1
