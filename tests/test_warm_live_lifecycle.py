"""Exercise real encoder pipes, failure cleanup and bounded warm-join buffering."""

import struct
import sys

import pytest

from app.utils.warm_live import (
    WarmLiveConfig,
    WarmLiveManager,
    WarmLiveStream,
    _Mp4BoxParser,
)


def box(kind, payload=b""):
    return struct.pack(">I4s", len(payload) + 8, kind.encode()) + payload


@pytest.mark.parametrize("chunk_size", [1, 7, 8, 13, 1024])
def test_fragmented_pipe_input_yields_only_complete_boxes(chunk_size):
    raw = box("ftyp", b"init") + struct.pack(">I4sQ", 1, b"mdat", 19) + b"abc"
    parser = _Mp4BoxParser()
    result = []
    for offset in range(0, len(raw), chunk_size):
        parser.feed(raw[offset : offset + chunk_size])
        result.extend(parser.boxes())
    assert [kind for kind, _ in result] == ["ftyp", "mdat"]
    assert b"".join(data for _, data in result) == raw


def test_corrupt_header_can_recover_on_next_input():
    parser = _Mp4BoxParser()
    parser.feed(struct.pack(">I4s", 4, b"mdat"))
    assert list(parser.boxes()) == []
    parser.feed(box("moof"))
    assert list(parser.boxes()) == [("moof", box("moof"))]


def encoder(payload=b"", exit_code=None):
    suffix = (
        "import time; time.sleep(10)" if exit_code is None else f"sys.exit({exit_code})"
    )
    return [
        sys.executable,
        "-S",
        "-c",
        f"import sys; sys.stdout.buffer.write({payload!r}); sys.stdout.buffer.flush(); {suffix}",
    ]


def test_subscriber_receives_init_and_fragment_then_releases_process():
    init = box("ftyp", b"test") + box("moov")
    fragment = box("moof") + box("mdat", b"frame")
    stream = WarmLiveStream(
        encoder(init + fragment), WarmLiveConfig(init_timeout_seconds=2)
    )
    subscriber = stream.subscribe()
    try:
        assert next(subscriber) == init
        assert next(subscriber) == fragment
        assert not stream.should_expire(float("inf"))
    finally:
        subscriber.close()
        stream.stop()
        if stream._thread:
            stream._thread.join(timeout=2)
    assert stream._subscribers == 0
    assert not stream._thread.is_alive()


@pytest.mark.parametrize("mode", ["exit", "stall", "idle"])
def test_failed_or_unused_encoders_are_reaped(mode):
    cfg = WarmLiveConfig(
        ttl_seconds=0.1, stall_timeout_seconds=0.1, init_timeout_seconds=2
    )
    stream = WarmLiveStream(encoder(exit_code=42 if mode == "exit" else None), cfg)
    try:
        if mode == "idle":
            stream.warm()
        else:
            assert list(stream.subscribe()) == []
        stream._thread.join(timeout=2)
        assert not stream._thread.is_alive()
        assert stream._proc is None
        assert stream._subscribers == 0
        if mode == "exit":
            assert stream.last_error() == "Live encoder exited with status 42"
        if mode == "stall":
            assert stream.last_error() == "Live encoder stopped producing data"
    finally:
        stream.stop()


def test_cache_obeys_byte_and_fragment_limits():
    stream = WarmLiveStream(
        [], WarmLiveConfig(max_cache_bytes=6, max_cached_fragments=2)
    )
    with stream._lock:
        for payload in [b"aa", b"bbb", b"cccc"]:
            stream._pending_frag = [payload]
            stream._finalize_fragment_locked()
    assert [data for _, data in stream._frags] == [b"cccc"]
    assert stream._frags_bytes == 4


def test_manager_reuses_live_entry_and_reaps_expired_process(monkeypatch):
    manager = WarmLiveManager(WarmLiveConfig(ttl_seconds=30))
    stream = manager.get_or_create("camera", encoder())
    assert manager.get_or_create("camera", encoder()) is stream
    stream.warm()
    process = stream._proc
    try:
        monkeypatch.setattr(stream, "should_expire", lambda now: True)
        manager._reap()
        assert "camera" not in manager._streams
        assert process.poll() is not None
    finally:
        stream.stop()
        stream._thread.join(timeout=2)


@pytest.mark.parametrize("transition", ["restart", "slow_consumer", "stop"])
def test_subscriber_ends_cleanly_at_stream_boundaries(monkeypatch, transition):
    stream = WarmLiveStream([], WarmLiveConfig())
    monkeypatch.setattr(stream, "_start_locked", lambda: None)
    stream._init = b"initialization"
    stream._init_ready = True
    stream._seq = 3
    stream._frags.extend([(1, b"one"), (2, b"two"), (3, b"three")])
    subscriber = stream.subscribe()
    assert [next(subscriber) for _ in range(4)] == [
        b"initialization",
        b"one",
        b"two",
        b"three",
    ]
    with stream._lock:
        if transition == "restart":
            stream._generation += 1
        elif transition == "slow_consumer":
            stream._frags.clear()
            stream._frags.append((6, b"too late"))
        else:
            stream._stopping = True
    assert list(subscriber) == []
    assert stream._subscribers == 0
