from unittest.mock import MagicMock, patch

from app.utils.http_probe import clear_probe_cache, probe_url_with_range


def _resp(status=200, url="http://example.com", headers=None, ok=True, history=None):
    r = MagicMock()
    r.status_code = status
    r.url = url
    r.headers = headers or {}
    r.ok = ok
    r.history = history or []
    r.content = b""

    def _iter_content(chunk_size=4096):
        data = r.content or b""
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    r.iter_content.side_effect = _iter_content
    return r


def _box(typ: bytes, payload: bytes) -> bytes:
    size = (8 + len(payload)).to_bytes(4, "big")
    return size + typ + payload


def _mvhd_v0(timescale: int, duration: int) -> bytes:
    payload = (
        b"\x00\x00\x00\x00"  # version + flags
        + (0).to_bytes(4, "big")  # creation time
        + (0).to_bytes(4, "big")  # modification time
        + int(timescale).to_bytes(4, "big")
        + int(duration).to_bytes(4, "big")
        + b"\x00" * 32
    )
    return _box(b"mvhd", payload)


def setup_function():
    clear_probe_cache()


def test_probe_url_with_range_reports_metadata_and_chain():
    h1 = _resp(status=301, url="http://a")
    h2 = _resp(status=302, url="http://b")
    final = _resp(
        status=206,
        url="http://c",
        headers={
            "Content-Type": "image/jpeg",
            "Accept-Ranges": "bytes",
            "Content-Range": "bytes 0-1/1234",
        },
        ok=True,
        history=[h1, h2],
    )
    with patch("app.utils.http_probe.requests.get", return_value=final):
        ok, info = probe_url_with_range("http://a", probe_mp4_atoms=False)

    assert ok is True
    assert info["status"] == 206
    assert info["content_type"] == "image/jpeg"
    assert info["accept_ranges"] == "bytes"
    assert info["content_range"] == "bytes 0-1/1234"
    assert info["redirect_chain"] == ["http://a", "http://b", "http://c"]


def test_probe_url_with_range_retries_without_range_on_416():
    first = _resp(status=416, url="http://x", headers={}, ok=False)
    second = _resp(
        status=200,
        url="http://x",
        headers={"Content-Type": "text/html"},
        ok=True,
    )

    with patch(
        "app.utils.http_probe.requests.get", side_effect=[first, second]
    ) as mock_get:
        ok, info = probe_url_with_range("http://x", probe_mp4_atoms=False)

    assert ok is True
    assert info["status"] == 200
    assert mock_get.call_count == 2


def test_probe_url_with_range_failure_returns_false():
    with patch("app.utils.http_probe.requests.get", side_effect=Exception("boom")):
        ok, info = probe_url_with_range("http://x", probe_mp4_atoms=False)
    assert ok is False
    assert info == {}


def test_probe_url_with_range_sends_conditional_headers_after_cache():
    first = _resp(
        status=200,
        url="http://example.com/media",
        headers={
            "Content-Type": "application/octet-stream",
            "ETag": '"abc123"',
            "Last-Modified": "Sat, 14 Feb 2026 20:00:00 GMT",
        },
        ok=True,
    )
    second = _resp(
        status=304,
        url="http://example.com/media",
        headers={},
        ok=True,
    )

    with patch(
        "app.utils.http_probe.requests.get", side_effect=[first, second]
    ) as mock_get:
        ok1, info1 = probe_url_with_range(
            "http://example.com/media", probe_mp4_atoms=False
        )
        ok2, info2 = probe_url_with_range(
            "http://example.com/media", probe_mp4_atoms=False
        )

    assert ok1 is True and info1["status"] == 200
    assert ok2 is True and info2["status"] == 304

    second_headers = mock_get.call_args_list[1].kwargs["headers"]
    assert second_headers["If-None-Match"] == '"abc123"'
    assert second_headers["If-Modified-Since"] == "Sat, 14 Feb 2026 20:00:00 GMT"


def test_probe_url_with_range_can_disable_conditional_cache():
    resp = _resp(
        status=200,
        url="http://example.com/no-cache",
        headers={"Content-Type": "text/html", "ETag": '"etag-1"'},
        ok=True,
    )

    with patch("app.utils.http_probe.requests.get", return_value=resp) as mock_get:
        probe_url_with_range(
            "http://example.com/no-cache",
            use_conditional_cache=False,
            probe_mp4_atoms=False,
        )

    sent_headers = mock_get.call_args.kwargs["headers"]
    assert "If-None-Match" not in sent_headers
    assert "If-Modified-Since" not in sent_headers


def test_mp4_probe_finds_moov_in_front_and_duration():
    base = _resp(
        status=206,
        url="http://example.com/video.mp4",
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": "bytes 0-1/999999",
        },
        ok=True,
    )

    ftyp = _box(b"ftyp", b"isom" + b"\x00" * 12)
    mvhd = _mvhd_v0(timescale=1000, duration=12345)
    moov = _box(b"moov", mvhd)
    front = _resp(
        status=206,
        url="http://example.com/video.mp4",
        headers={"Content-Type": "video/mp4"},
        ok=True,
    )
    front.content = ftyp + moov

    with patch(
        "app.utils.http_probe.requests.get",
        side_effect=[
            base,
            _resp(
                status=206,
                url="http://example.com/video.mp4",
                headers={"Content-Type": "video/mp4"},
                ok=True,
            ),
            front,
        ],
    ):
        ok, info = probe_url_with_range("http://example.com/video.mp4")

    assert ok is True
    mp4 = info.get("mp4_probe") or {}
    assert mp4.get("ftyp") is True
    assert mp4.get("moov") == "front"
    assert abs(float(mp4.get("duration_seconds")) - 12.345) < 0.01


def test_mp4_probe_hunts_tail_when_moov_not_in_front():
    base = _resp(
        status=206,
        url="http://example.com/audio.m4a",
        headers={
            "Content-Type": "audio/mp4",
            "Content-Range": "bytes 0-1/500000",
        },
        ok=True,
    )

    ftyp = _box(b"ftyp", b"isom" + b"\x00" * 12)
    # Large mdat that does not fit in sampled front bytes.
    mdat_header = (10_000_000).to_bytes(4, "big") + b"mdat"
    front = _resp(
        status=206,
        url="http://example.com/audio.m4a",
        headers={"Content-Type": "audio/mp4"},
        ok=True,
    )
    front.content = ftyp + mdat_header

    mvhd = _mvhd_v0(timescale=48000, duration=96000)
    moov = _box(b"moov", mvhd)
    tail = _resp(
        status=206,
        url="http://example.com/audio.m4a",
        headers={"Content-Type": "audio/mp4"},
        ok=True,
    )
    tail.content = moov

    with patch(
        "app.utils.http_probe.requests.get",
        side_effect=[
            base,
            _resp(
                status=206,
                url="http://example.com/audio.m4a",
                headers={"Content-Type": "audio/mp4"},
                ok=True,
            ),
            front,
            tail,
        ],
    ):
        ok, info = probe_url_with_range("http://example.com/audio.m4a")

    assert ok is True
    mp4 = info.get("mp4_probe") or {}
    assert mp4.get("moov") == "tail"
    assert abs(float(mp4.get("duration_seconds")) - 2.0) < 0.01


def test_probe_url_with_range_keeps_range_across_redirects():
    r1 = _resp(
        status=302,
        url="http://example.com/start",
        headers={"Location": "http://cdn.example.com/file.mp4"},
        ok=False,
    )
    r2 = _resp(
        status=206,
        url="http://cdn.example.com/file.mp4",
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": "bytes 0-1/100000",
        },
        ok=True,
    )
    # Extra front probe response for mp4 atom check.
    r3 = _resp(
        status=206,
        url="http://cdn.example.com/file.mp4",
        headers={"Content-Type": "video/mp4"},
        ok=True,
    )
    r3.content = b""

    with patch(
        "app.utils.http_probe.requests.get", side_effect=[r1, r2, r3]
    ) as mock_get:
        ok, info = probe_url_with_range(
            "http://example.com/start", probe_mp4_atoms=False
        )

    assert ok is True
    assert info["status"] == 206
    assert info["redirect_chain"] == [
        "http://example.com/start",
        "http://cdn.example.com/file.mp4",
    ]
    first_headers = mock_get.call_args_list[0].kwargs["headers"]
    second_headers = mock_get.call_args_list[1].kwargs["headers"]
    assert first_headers.get("Range") == "bytes=0-1"
    assert second_headers.get("Range") == "bytes=0-1"


def test_probe_retry_ladder_suffix_tail_fallback():
    # Attempt 1: suffix range fails with 416 and total-length hint.
    a1 = _resp(
        status=416,
        url="http://example.com/blob.bin",
        headers={"Content-Range": "bytes */4096"},
        ok=False,
    )
    # Attempt 2: plain GET still fails.
    a2 = _resp(status=503, url="http://example.com/blob.bin", headers={}, ok=False)
    # Attempt 3: computed absolute tail range succeeds.
    a3 = _resp(
        status=206,
        url="http://example.com/blob.bin",
        headers={"Content-Type": "application/octet-stream"},
        ok=True,
    )

    with patch(
        "app.utils.http_probe.requests.get", side_effect=[a1, a2, a3]
    ) as mock_get:
        ok, info = probe_url_with_range(
            "http://example.com/blob.bin",
            range_header="bytes=-1024",
            probe_mp4_atoms=False,
        )

    assert ok is True
    assert info["status"] == 206
    steps = [a["step"] for a in info.get("probe_attempts", [])]
    assert steps == ["micro_range", "micro_get", "computed_tail"]
    third_headers = mock_get.call_args_list[2].kwargs["headers"]
    assert third_headers["Range"] == "bytes=3072-4095"
