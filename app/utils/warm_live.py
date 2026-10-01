from __future__ import annotations

import collections
import os
import selectors
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Deque, Dict, Generator, Optional, Tuple


class _Mp4BoxParser:
    """Incremental ISO-BMFF box parser for fragmented MP4 streaming.

    We only need enough structure to split the ffmpeg output into whole boxes so
    we can:
    - capture the init segment (ftyp/moov/...) once
    - cache a few recent fragments (moof+mdat...) for warm-join

    This intentionally supports only the common cases produced by ffmpeg.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)

    def _try_read_box(self) -> Optional[Tuple[str, bytes]]:
        if len(self._buf) < 8:
            return None
        size = struct.unpack(">I", self._buf[0:4])[0]
        boxtype = bytes(self._buf[4:8])
        header = 8
        if size == 1:
            if len(self._buf) < 16:
                return None
            size = struct.unpack(">Q", self._buf[8:16])[0]
            header = 16
        if size == 0:
            # "extends to end of file" - not expected for fMP4 over pipe. Treat
            # whatever we have as incomplete.
            return None
        if size < header:
            # Corrupt stream; drop buffer to avoid infinite growth.
            self._buf.clear()
            return None
        if len(self._buf) < size:
            return None
        raw = bytes(self._buf[:size])
        del self._buf[:size]
        try:
            t = boxtype.decode("ascii", errors="replace")
        except Exception:
            t = "????"
        return t, raw

    def boxes(self) -> Generator[Tuple[str, bytes], None, None]:
        while True:
            item = self._try_read_box()
            if item is None:
                return
            yield item


@dataclass
class WarmLiveConfig:
    ttl_seconds: float = 30.0
    init_timeout_seconds: float = 8.0
    max_cache_bytes: int = 2_000_000
    max_cached_fragments: int = 6
    stall_timeout_seconds: float = 20.0


class WarmLiveStream:
    def __init__(self, cmd: list[str], cfg: WarmLiveConfig) -> None:
        self._cmd = cmd
        self._cfg = cfg

        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

        self._init = b""
        self._init_ready = False
        self._pending_frag: list[bytes] = []
        self._frags: Deque[Tuple[int, bytes]] = collections.deque()
        self._frags_bytes = 0
        self._seq = 0
        self._generation = 0

        self._subscribers = 0
        self._last_use = time.monotonic()
        self._stopping = False
        self._last_err = ""

    def _start_locked(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self._stopping = False
        self._last_err = ""
        # Reset cached stream state on restart: new init segment.
        self._init = b""
        self._init_ready = False
        self._pending_frag = []
        self._frags.clear()
        self._frags_bytes = 0
        self._seq += 1
        self._generation += 1
        # Never leave an unread stderr pipe: FFmpeg can fill it and deadlock.
        # Raw diagnostics can contain camera credentials; retain only exit status.
        self._proc = subprocess.Popen(
            self._cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
        )
        self._thread = threading.Thread(
            target=self._run, args=(self._proc,), daemon=True
        )
        self._thread.start()

    def _stop_locked(self) -> subprocess.Popen | None:
        self._stopping = True
        p = self._proc
        self._proc = None
        self._cv.notify_all()
        return p

    @staticmethod
    def _terminate(p: subprocess.Popen | None) -> None:
        """Reap the child without holding stream or manager locks."""
        if not p:
            return
        try:
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
        try:
            p.wait(timeout=1)
        except Exception:
            pass

    def _trim_locked(self) -> None:
        while self._frags and (
            self._frags_bytes > self._cfg.max_cache_bytes
            or len(self._frags) > self._cfg.max_cached_fragments
        ):
            _, b = self._frags.popleft()
            self._frags_bytes -= len(b)

    def _finalize_fragment_locked(self) -> None:
        if not self._pending_frag:
            return
        frag = b"".join(self._pending_frag)
        self._pending_frag = []
        if not frag:
            return
        self._seq += 1
        self._frags.append((self._seq, frag))
        self._frags_bytes += len(frag)
        self._trim_locked()
        self._cv.notify_all()

    def _run(self, p: subprocess.Popen) -> None:
        parser = _Mp4BoxParser()
        last_data = time.monotonic()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(p.stdout, selectors.EVENT_READ)
                while True:
                    with self._lock:
                        if self._proc is not p or self._stopping:
                            return
                        if (
                            not self._subscribers
                            and time.monotonic() - self._last_use
                            >= self._cfg.ttl_seconds
                        ):
                            self._stop_locked()
                            return
                        if (
                            time.monotonic() - last_data
                            >= self._cfg.stall_timeout_seconds
                        ):
                            self._last_err = "Live encoder stopped producing data"
                            return
                    # Read available bytes, not a full 64 KiB buffered read.
                    # Polling also expires silent sources without another request.
                    if not selector.select(timeout=0.1):
                        continue
                    chunk = os.read(p.stdout.fileno(), 64 * 1024)
                    if not chunk:
                        return
                    last_data = time.monotonic()
                    parser.feed(chunk)
                    for boxtype, raw in parser.boxes():
                        with self._lock:
                            if self._proc is not p:
                                return
                            if not self._init_ready:
                                if boxtype == "moof":
                                    self._init_ready = True
                                    self._pending_frag = [raw]
                                    self._cv.notify_all()
                                else:
                                    self._init += raw
                                continue
                            if boxtype == "moof":
                                self._pending_frag = [raw]
                            elif self._pending_frag:
                                self._pending_frag.append(raw)
                                if boxtype == "mdat":
                                    # FFmpeg emits one mdat per moof. Publish now,
                                    # without waiting for the next keyframe.
                                    self._finalize_fragment_locked()
        except (OSError, ValueError):
            with self._lock:
                if self._proc is p:
                    self._last_err = "Live stream pipe failed"
        finally:
            with self._lock:
                if self._proc is p:
                    rc = p.poll()
                    if rc not in (None, 0):
                        self._last_err = f"Live encoder exited with status {rc}"
                    self._stop_locked()
            self._terminate(p)
            if p.stdout:
                p.stdout.close()

    def warm(self) -> None:
        """Start or renew a stream's idle lease."""
        with self._lock:
            self._last_use = time.monotonic()
            self._start_locked()

    def subscribe(self) -> Generator[bytes, None, None]:
        """Yield init and each fragment once, releasing the lease on every exit."""
        deadline = time.monotonic() + float(self._cfg.init_timeout_seconds or 0)
        registered = False
        try:
            with self._lock:
                self._subscribers += 1
                registered = True
                self._last_use = time.monotonic()
                self._start_locked()
                p = self._proc
                generation = self._generation
                while not self._init_ready:
                    if self._proc is not p or self._stopping:
                        return
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return
                    self._cv.wait(timeout=min(0.1, remaining))
                start_seq = self._seq
                init = self._init
                snap = list(self._frags)[-3:]
            if init:
                yield init
            for _, frag in snap:
                if frag:
                    yield frag

            while True:
                with self._lock:
                    if self._generation != generation:
                        return
                    if self._frags and start_seq < self._frags[0][0] - 1:
                        # A slow consumer fell outside the bounded cache. End
                        # this generation so the player reconnects cleanly.
                        return
                    frags = [
                        (seq, frag) for seq, frag in self._frags if seq > start_seq
                    ]
                    if not frags:
                        if self._stopping:
                            return
                        self._cv.wait(timeout=0.1)
                        continue
                    start_seq = frags[-1][0]
                for _, frag in frags:
                    if frag:
                        yield frag
        finally:
            if registered:
                with self._lock:
                    self._subscribers -= 1
                    self._last_use = time.monotonic()

    def should_expire(self, now: float) -> bool:
        """Check the idle lease using a monotonic timestamp."""
        with self._lock:
            if self._subscribers > 0:
                return False
            return (now - self._last_use) >= self._cfg.ttl_seconds

    def stop(self) -> None:
        """Wake subscribers and reap the encoder without blocking their lock."""
        with self._lock:
            p = self._stop_locked()
        self._terminate(p)

    def last_error(self) -> str:
        """Return a credential-free encoder failure description."""
        with self._lock:
            return self._last_err


class WarmLiveManager:
    def __init__(self, cfg: WarmLiveConfig | None = None) -> None:
        self._cfg = cfg or WarmLiveConfig()
        self._lock = threading.Lock()
        self._streams: Dict[str, WarmLiveStream] = {}

    def get_or_create(self, key: str, cmd: list[str]) -> WarmLiveStream:
        with self._lock:
            s = self._streams.get(key)
            if s is None:
                s = WarmLiveStream(cmd, self._cfg)
                self._streams[key] = s
            return s

    def warm(self, key: str, cmd: list[str]) -> None:
        self._reap()
        with self._lock:
            s = self._streams.setdefault(key, WarmLiveStream(cmd, self._cfg))
            s.warm()

    def subscribe(self, key: str, cmd: list[str]) -> Generator[bytes, None, None]:
        self._reap()
        with self._lock:
            s = self._streams.setdefault(key, WarmLiveStream(cmd, self._cfg))
            s.warm()
        yield from s.subscribe()

    def _reap(self) -> None:
        now = time.monotonic()
        processes = []
        with self._lock:
            expired = [k for k, s in self._streams.items() if s.should_expire(now)]
            for k in expired:
                s = self._streams.pop(k, None)
                if s:
                    with s._lock:
                        processes.append(s._stop_locked())
        for p in processes:
            WarmLiveStream._terminate(p)
