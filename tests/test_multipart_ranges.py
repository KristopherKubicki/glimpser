import pytest

from app.utils.http_probe import _parse_multipart_byteranges


def part(start, body, total=1000):
    return (
        b"--sample\r\nContent-Type: video/mp4\r\nContent-Range: bytes "
        + str(start).encode()
        + b"-"
        + str(start + len(body) - 1).encode()
        + b"/"
        + str(total).encode()
        + b"\r\n\r\n"
        + body
        + b"\r\n"
    )


@pytest.mark.parametrize(
    "body",
    [
        b"\x00mp4\r\n",
        b"\t binary \t",
        b"payload--sampleinside",
        b"payload\r\n--sample\r\ninside",
    ],
)
def test_binary_range_is_preserved_exactly(body):
    payload = part(0, body) + part(100, b"tail\r\n") + b"--sample--\r\n"
    assert _parse_multipart_byteranges(
        payload, 'multipart/byteranges; boundary="sample"'
    ) == {0: body, 100: b"tail\r\n"}


def test_truncated_body_is_not_accepted():
    payload = (
        b"--sample\r\nContent-Range: bytes 0-99/100\r\n\r\nshort\r\n--sample--\r\n"
    )
    assert (
        _parse_multipart_byteranges(payload, "multipart/byteranges; boundary=sample")
        == {}
    )


@pytest.mark.parametrize("range_value", [b"10-5/100", b"90-110/100"])
def test_invalid_range_is_not_accepted(range_value):
    payload = (
        b"--sample\r\nContent-Range: bytes "
        + range_value
        + b"\r\n\r\ndata\r\n--sample--\r\n"
    )
    assert (
        _parse_multipart_byteranges(payload, "multipart/byteranges; boundary=sample")
        == {}
    )


def test_complete_prefix_survives_truncated_second_part():
    payload = (
        part(0, b"valid")
        + b"--sample\r\nContent-Range: bytes 100-120/1000\r\n\r\nshort"
    )
    assert _parse_multipart_byteranges(
        payload, "multipart/byteranges; boundary=sample"
    ) == {0: b"valid"}
