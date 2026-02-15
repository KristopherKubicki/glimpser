from __future__ import annotations

import collections
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
        self._frags: Deque[bytes] = collections.deque()
        self._frags_bytes = 0
        self._seq = 0

        self._subscribers = 0
        self._last_use = time.time()
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
        self._proc = subprocess.Popen(
            self._cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _stop_locked(self) -> None:
        self._stopping = True
        p = self._proc
        self._proc = None
        if not p:
            return
        try:
            if p.stdout:
                p.stdout.close()
        except Exception:
            pass
        try:
            if p.stderr:
                raw = p.stderr.read(4096)
                if raw:
                    self._last_err = raw.decode(errors="replace").strip()
                p.stderr.close()
        except Exception:
            pass
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
            b = self._frags.popleft()
            self._frags_bytes -= len(b)

    def _finalize_fragment_locked(self) -> None:
        if not self._pending_frag:
            return
        frag = b"".join(self._pending_frag)
        self._pending_frag = []
        if not frag:
            return
        self._frags.append(frag)
        self._frags_bytes += len(frag)
        self._trim_locked()
        self._seq += 1
        self._cv.notify_all()

    def _run(self) -> None:
        parser = _Mp4BoxParser()
        while True:
            with self._lock:
                p = self._proc
                stopping = self._stopping
            if not p or stopping:
                return

            try:
                chunk = p.stdout.read(64 * 1024) if p.stdout else b""
            except Exception:
                chunk = b""

            if not chunk:
                try:
                    rc = p.poll()
                except Exception:
                    rc = 1
                if rc is None:
                    time.sleep(0.05)
                    continue
                with self._lock:
                    try:
                        if p.stderr:
                            raw = p.stderr.read(4096)
                            if raw:
                                self._last_err = raw.decode(errors="replace").strip()
                    except Exception:
                        pass
                    self._seq += 1
                    self._cv.notify_all()
                return

            parser.feed(chunk)
            for boxtype, raw in parser.boxes():
                with self._lock:
                    self._last_use = time.time()
                    if not self._init_ready:
                        if boxtype == "moof":
                            self._init_ready = True
                            self._pending_frag = [raw]
                            self._seq += 1
                            self._cv.notify_all()
                        else:
                            self._init += raw
                        continue

                    if boxtype == "moof":
                        self._finalize_fragment_locked()
                        self._pending_frag = [raw]
                    else:
                        self._pending_frag.append(raw)

    def warm(self) -> None:
        with self._lock:
            self._last_use = time.time()
            self._start_locked()

    def subscribe(self) -> Generator[bytes, None, None]:
        # If a client subscribes before we have the init segment, wait briefly
        # so playback can start without needing a second request.
        deadline = time.time() + float(self._cfg.init_timeout_seconds or 0)

        with self._lock:
            self._subscribers += 1
            self._last_use = time.time()
            self._start_locked()

            while not self._init_ready:
                if self._proc and self._proc.poll() is not None:
                    return
                remaining = deadline - time.time()
                if remaining <= 0:
                    return
                self._cv.wait(timeout=min(1.0, remaining))

            start_seq = self._seq
            init = self._init
            snap = list(self._frags)[-3:]

        try:
            if init:
                yield init
            for frag in snap:
                if frag:
                    yield frag

            while True:
                with self._lock:
                    self._last_use = time.time()
                    if (
                        self._proc
                        and self._proc.poll() is not None
                        and start_seq == self._seq
                    ):
                        return
                    self._cv.wait(timeout=1.0)
                    if start_seq != self._seq:
                        frags = list(self._frags)[-3:]
                        start_seq = self._seq
                    else:
                        frags = []
                for frag in frags:
                    if frag:
                        yield frag
        finally:
            with self._lock:
                self._subscribers = max(0, self._subscribers - 1)

    def should_expire(self, now: float) -> bool:
        with self._lock:
            if self._subscribers > 0:
                return False
            return (now - self._last_use) >= self._cfg.ttl_seconds

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def last_error(self) -> str:
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
        self.get_or_create(key, cmd).warm()
        self._reap()

    def subscribe(self, key: str, cmd: list[str]) -> Generator[bytes, None, None]:
        s = self.get_or_create(key, cmd)
        self._reap()
        yield from s.subscribe()

    def _reap(self) -> None:
        now = time.time()
        with self._lock:
            expired = [k for k, s in self._streams.items() if s.should_expire(now)]
            for k in expired:
                s = self._streams.pop(k, None)
                if s:
                    s.stop()
