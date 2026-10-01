"""Small HTTP probe helpers used by connectivity/preflight checks."""

from __future__ import annotations

import os
import re
import socket
import ssl
import time
from collections import OrderedDict
from threading import Lock
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_MEDIA_ACCEPT = "audio/*, application/octet-stream;q=0.9, */*;q=0.1"
PROBE_CACHE_TTL_SECONDS = 3600
PROBE_CACHE_MAX_ENTRIES = 1024
PROBE_CACHE_MAX_ENTRY_CHARS = 8192
MP4_PROBE_FRONT_BYTES = 128 * 1024
MP4_PROBE_TAIL_BYTES = 128 * 1024
MP4_MULTI_RANGE_MAX_BYTES = 384 * 1024

_probe_conditional_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
_probe_cache_lock = Lock()


def _reset_probe_cache_after_fork() -> None:
    # A capture child must not inherit a lock held by a vanished parent thread.
    global _probe_cache_lock
    _probe_cache_lock = Lock()
    _probe_conditional_cache.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_probe_cache_after_fork)


def _cache_get(url: str) -> dict[str, Any] | None:
    with _probe_cache_lock:
        entry = _probe_conditional_cache.get(url)
        if entry is None:
            return None
        if time.monotonic() - entry["time"] >= PROBE_CACHE_TTL_SECONDS:
            _probe_conditional_cache.pop(url, None)
            return None
        return dict(entry)


def _cache_set(url: str, *, etag: str = "", last_modified: str = "") -> None:
    with _probe_cache_lock:
        # A successful response without validators supersedes any old value.
        _probe_conditional_cache.pop(url, None)
        now = time.monotonic()
        # Entries are ordered by write time, so expired entries form a prefix.
        while _probe_conditional_cache:
            oldest = next(iter(_probe_conditional_cache))
            if now - _probe_conditional_cache[oldest]["time"] < PROBE_CACHE_TTL_SECONDS:
                break
            _probe_conditional_cache.popitem(last=False)
        if not etag and not last_modified:
            return
        if len(url) + len(etag) + len(last_modified) > PROBE_CACHE_MAX_ENTRY_CHARS:
            return
        _probe_conditional_cache[url] = {
            "etag": etag,
            "last_modified": last_modified,
            "time": now,
        }
        while len(_probe_conditional_cache) > PROBE_CACHE_MAX_ENTRIES:
            _probe_conditional_cache.popitem(last=False)


def clear_probe_cache() -> None:
    """Clear in-memory conditional probe cache (tests/maintenance)."""

    with _probe_cache_lock:
        _probe_conditional_cache.clear()


def _parse_content_length_from_range(content_range: str) -> int | None:
    # Example: "bytes 0-1/12345"
    if "/" not in content_range:
        return None
    total = content_range.rsplit("/", 1)[-1].strip()
    if not total or total == "*":
        return None
    try:
        value = int(total)
        return value if value > 0 else None
    except ValueError:
        return None


def _looks_like_mp4(url: str, content_type: str) -> bool:
    u = (url or "").lower()
    c = (content_type or "").lower()
    if any(ext in u for ext in (".mp4", ".m4a", ".m4v", ".mov", ".ismv")):
        return True
    return any(
        token in c
        for token in (
            "video/mp4",
            "audio/mp4",
            "application/mp4",
            "video/quicktime",
        )
    )


def _parse_mp4_boxes(data: bytes) -> list[dict[str, int | str]]:
    boxes: list[dict[str, int | str]] = []
    pos = 0
    n = len(data)
    while pos + 8 <= n:
        size = int.from_bytes(data[pos : pos + 4], "big")
        typ = data[pos + 4 : pos + 8].decode("latin-1", errors="ignore")
        header = 8
        if size == 1:
            if pos + 16 > n:
                break
            size = int.from_bytes(data[pos + 8 : pos + 16], "big")
            header = 16
        elif size == 0:
            size = n - pos

        if size < header:
            break

        end = pos + size
        boxes.append(
            {
                "type": typ,
                "start": pos,
                "size": size,
                "header": header,
                "complete": 1 if end <= n else 0,
            }
        )
        if end <= pos:
            break
        pos = end
        if end > n:
            break
    return boxes


def _extract_mp4_duration_seconds(moov_payload: bytes) -> float | None:
    # Look for mvhd child box inside moov.
    i = 0
    n = len(moov_payload)
    while i + 8 <= n:
        size = int.from_bytes(moov_payload[i : i + 4], "big")
        typ = moov_payload[i + 4 : i + 8]
        header = 8
        if size == 1:
            if i + 16 > n:
                return None
            size = int.from_bytes(moov_payload[i + 8 : i + 16], "big")
            header = 16
        elif size == 0:
            size = n - i

        if size < header or i + size > n:
            return None

        if typ == b"mvhd":
            payload = moov_payload[i + header : i + size]
            if len(payload) < 20:
                return None
            version = payload[0]
            if version == 0:
                if len(payload) < 20:
                    return None
                timescale = int.from_bytes(payload[12:16], "big")
                duration = int.from_bytes(payload[16:20], "big")
            elif version == 1:
                if len(payload) < 32:
                    return None
                timescale = int.from_bytes(payload[20:24], "big")
                duration = int.from_bytes(payload[24:32], "big")
            else:
                return None
            if timescale <= 0:
                return None
            return float(duration) / float(timescale)

        i += size

    return None


def _remaining_probe_timeout(timeout: float, deadline: float | None) -> float:
    """Return the remaining request-chain budget without restarting its clock."""
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise requests.Timeout("HTTP probe deadline exceeded")
    return min(timeout, remaining)


def _get_with_redirects(
    url: str,
    request_kwargs: dict[str, Any],
    max_redirects: int = 6,
    deadline: float | None = None,
) -> tuple[requests.Response, list[str]]:
    """Perform GET while preserving headers (including Range) across redirects."""

    current = url
    request_kwargs = dict(request_kwargs)
    request_kwargs["headers"] = dict(request_kwargs.get("headers") or {})
    chain: list[str] = []

    for _ in range(max_redirects + 1):
        kwargs = dict(request_kwargs)
        kwargs["allow_redirects"] = False
        kwargs["timeout"] = _remaining_probe_timeout(
            request_kwargs["timeout"], deadline
        )
        resp = requests.get(current, **kwargs)

        effective = str(getattr(resp, "url", current) or current)
        chain.append(effective)
        status = int(getattr(resp, "status_code", 0) or 0)

        if status in {301, 302, 303, 307, 308}:
            location = str(resp.headers.get("Location") or "").strip()
            if not location:
                return resp, chain
            try:
                destination = urljoin(effective, location)
                old, new = urlparse(effective), urlparse(destination)

                def origin(parsed):
                    return (
                        parsed.scheme.lower(),
                        parsed.hostname,
                        parsed.port
                        or (443 if parsed.scheme.lower() == "https" else 80),
                    )

                if origin(old) != origin(new):
                    # Range survives redirects; source credentials and validators
                    # must not cross an origin boundary or reappear on later hops.
                    request_kwargs.pop("auth", None)
                    request_kwargs.pop("cookies", None)
                    request_kwargs["headers"] = {
                        key: value
                        for key, value in request_kwargs["headers"].items()
                        if key.lower()
                        not in {
                            "authorization",
                            "proxy-authorization",
                            "cookie",
                            "if-none-match",
                            "if-modified-since",
                            "host",
                        }
                    }
                current = destination
            finally:
                resp.close()
            continue

        return resp, chain

    # Every redirect response was closed; exhaustion is not a healthy 3xx.
    raise requests.TooManyRedirects("redirect limit exceeded")


def _parse_multipart_byteranges(payload: bytes, content_type: str) -> dict[int, bytes]:
    """Parse ``multipart/byteranges`` payload into ``start->bytes`` map."""

    ct = content_type or ""
    m = re.search(r"boundary=([^;]+)", ct, flags=re.IGNORECASE)
    if not m:
        return {}
    boundary = m.group(1).strip().strip('"')
    if not boundary:
        return {}

    try:
        marker = ("--" + boundary).encode("ascii")
    except UnicodeEncodeError:
        return {}
    if len(boundary) > 70 or "\r" in boundary or "\n" in boundary:
        return {}
    delimiter = re.compile(rb"(?:\A|\r\n)" + re.escape(marker) + rb"(\r\n|--)")
    out: dict[int, bytes] = {}
    position = 0
    while match := delimiter.search(payload, position):
        if match.group(1) == b"--":
            break
        header_start = match.end()
        header_end = payload.find(b"\r\n\r\n", header_start)
        if header_end < 0 or header_end - header_start > 64 * 1024:
            break
        headers = payload[header_start:header_end]
        content_range = re.search(
            rb"^Content-Range:[ \t]*bytes[ \t]+(\d+)-(\d+)/(\d+|\*)[ \t]*\r?$",
            headers,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not content_range:
            break
        start, end = int(content_range[1]), int(content_range[2])
        if end < start or (content_range[3] != b"*" and end >= int(content_range[3])):
            break
        body_start = header_end + 4
        body_end = body_start + end - start + 1
        # Content-Range frames the binary body. Never strip bytes or split on
        # a marker embedded inside media; verify the following MIME delimiter.
        following = delimiter.match(payload, body_end)
        if body_end > len(payload) or following is None:
            break
        out[start] = payload[body_start:body_end]
        position = body_end
    return out


def _fetch_sparse_multi_ranges(
    url: str,
    *,
    timeout: float,
    allow_redirects: bool,
    headers: dict[str, str],
    auth: Any,
    verify: bool | str | None,
    range_header: str,
    deadline: float | None = None,
) -> dict[int, bytes]:
    """Fetch sparse multi-range sample and parse multipart byte ranges."""

    h = dict(headers)
    h["Range"] = range_header
    h["Accept-Encoding"] = "identity"
    kwargs: dict[str, Any] = {
        "timeout": _remaining_probe_timeout(timeout, deadline),
        "allow_redirects": allow_redirects,
        "headers": h,
        "stream": True,
    }
    if auth is not None:
        kwargs["auth"] = auth
    if verify is not None:
        kwargs["verify"] = verify

    r = requests.get(url, **kwargs)
    try:
        if r.status_code != 206 or str(
            r.headers.get("Content-Encoding", "identity")
        ).lower() not in {"", "identity"}:
            return {}
        ct = str(r.headers.get("Content-Type", ""))
        if "multipart/byteranges" not in ct.lower():
            return {}

        buf = bytearray()
        for chunk in r.iter_content(chunk_size=8192):
            _remaining_probe_timeout(timeout, deadline)
            if not chunk:
                continue
            remaining = MP4_MULTI_RANGE_MAX_BYTES - len(buf)
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                buf.extend(chunk[:remaining])
                break
            buf.extend(chunk)

        return _parse_multipart_byteranges(bytes(buf), ct)
    finally:
        r.close()


def _fetch_range_chunk(
    url: str,
    *,
    timeout: float,
    allow_redirects: bool,
    headers: dict[str, str],
    auth: Any,
    verify: bool | str | None,
    range_header: str,
    deadline: float | None = None,
) -> bytes:
    requested = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header.strip(), re.I)
    if requested is None:
        return b""
    start, end = map(int, requested.groups())
    max_bytes = end - start + 1
    if max_bytes <= 0 or max_bytes > max(MP4_PROBE_FRONT_BYTES, MP4_PROBE_TAIL_BYTES):
        return b""
    h = dict(headers)
    h["Range"] = range_header
    h["Accept-Encoding"] = "identity"
    kwargs: dict[str, Any] = {
        "timeout": _remaining_probe_timeout(timeout, deadline),
        "allow_redirects": allow_redirects,
        "headers": h,
        "stream": True,
    }
    if auth is not None:
        kwargs["auth"] = auth
    if verify is not None:
        kwargs["verify"] = verify

    r = requests.get(url, **kwargs)
    try:
        if r.headers.get("Content-Encoding", "identity").strip().lower() not in {
            "",
            "identity",
        }:
            return b""
        if r.status_code == 206:
            returned = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+|\*)",
                r.headers.get("Content-Range", "").strip(),
                re.I,
            )
            if returned is None:
                return b""
            actual_start, actual_end = int(returned[1]), int(returned[2])
            if actual_start != start or not start <= actual_end <= end:
                return b""
            if returned[3] != "*" and actual_end >= int(returned[3]):
                return b""
            max_bytes = actual_end - actual_start + 1
        elif r.status_code != 200 or start != 0:
            # A server ignoring Range returns the beginning of the resource.
            # That is usable only for a bounded prefix, never a tail sample.
            return b""
        buf = bytearray()
        for chunk in r.iter_content(chunk_size=4096):
            _remaining_probe_timeout(timeout, deadline)
            if not chunk:
                continue
            buf.extend(chunk[: max_bytes - len(buf)])
            if len(buf) >= max_bytes:
                break
        if r.status_code == 206 and len(buf) != max_bytes:
            return b""
        return bytes(buf)
    finally:
        r.close()


def _probe_mp4_atoms(
    *,
    url: str,
    effective_url: str,
    content_type: str,
    content_range: str,
    timeout: float,
    allow_redirects: bool,
    headers: dict[str, str],
    auth: Any,
    verify: bool | str | None,
    deadline: float | None = None,
) -> dict[str, Any]:
    if not _looks_like_mp4(effective_url or url, content_type):
        return {}

    info: dict[str, Any] = {
        "format": "mp4-family",
        "moov": "unknown",
        "ftyp": False,
    }
    total_len = _parse_content_length_from_range(content_range)
    if total_len is not None:
        info["content_length"] = total_len

    front_end = max(0, MP4_PROBE_FRONT_BYTES - 1)
    front = b""
    tail = b""

    if total_len is not None and total_len > MP4_PROBE_TAIL_BYTES:
        tail_start = max(0, total_len - MP4_PROBE_TAIL_BYTES)
        sparse_header = f"bytes=0-{front_end},{tail_start}-{total_len - 1}"
        parts = _fetch_sparse_multi_ranges(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            headers=headers,
            auth=auth,
            verify=verify,
            deadline=deadline,
            range_header=sparse_header,
        )
        if parts:
            front = parts.get(0, b"")
            tail = parts.get(tail_start, b"")
            info["sparse_probe"] = "multi-range"

    if not front:
        front = _fetch_range_chunk(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            headers=headers,
            auth=auth,
            verify=verify,
            deadline=deadline,
            range_header=f"bytes=0-{front_end}",
        )
    if not front:
        return info

    front_boxes = _parse_mp4_boxes(front)
    info["ftyp"] = any(b.get("type") == "ftyp" for b in front_boxes)

    moov_front = next((b for b in front_boxes if b.get("type") == "moov"), None)
    if moov_front and int(moov_front.get("complete") or 0) == 1:
        start = int(moov_front["start"])
        header = int(moov_front["header"])
        size = int(moov_front["size"])
        moov_payload = front[start + header : start + size]
        info["moov"] = "front"
        info["moov_offset"] = start
        duration = _extract_mp4_duration_seconds(moov_payload)
        if duration is not None:
            info["duration_seconds"] = round(duration, 3)
        return info

    if total_len is None or total_len <= MP4_PROBE_TAIL_BYTES:
        info["moov"] = "missing"
        return info

    if not tail:
        tail_start = max(0, total_len - MP4_PROBE_TAIL_BYTES)
        tail = _fetch_range_chunk(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            headers=headers,
            auth=auth,
            verify=verify,
            deadline=deadline,
            range_header=f"bytes={tail_start}-{total_len - 1}",
        )
    if not tail:
        info["moov"] = "missing"
        return info

    tail_boxes = _parse_mp4_boxes(tail)
    moov_tail = next((b for b in tail_boxes if b.get("type") == "moov"), None)
    if moov_tail and int(moov_tail.get("complete") or 0) == 1:
        start = int(moov_tail["start"])
        header = int(moov_tail["header"])
        size = int(moov_tail["size"])
        moov_payload = tail[start + header : start + size]
        info["moov"] = "tail"
        info["moov_offset"] = tail_start + start
        duration = _extract_mp4_duration_seconds(moov_payload)
        if duration is not None:
            info["duration_seconds"] = round(duration, 3)
    else:
        info["moov"] = "missing"

    return info


def _connect_resolved(addrinfo, timeout: float, deadline: float) -> socket.socket:
    """Try resolved addresses once, transferring ownership only on success."""

    last_error = None
    for family, socktype, proto, _, address in addrinfo:
        remaining = _remaining_probe_timeout(timeout, deadline)
        sock = None
        connected = False
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(remaining)
            sock.connect(address)
            connected = True
            return sock
        except OSError as exc:
            last_error = exc
        finally:
            if sock is not None and not connected:
                sock.close()
    if last_error is not None:
        raise last_error
    raise OSError("No address candidates")


def _preconnect_check(
    url: str, timeout: float = 2.0, verify: bool | str | None = None
) -> tuple[bool, str]:
    """Run DNS + TCP (and optional TLS) checks before HTTP probing."""

    deadline = time.monotonic() + timeout
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False, "invalid_host"

    scheme = (parsed.scheme or "").lower()
    if scheme == "https":
        default_port = 443
    elif scheme == "http":
        default_port = 80
    elif scheme == "rtsp":
        default_port = 554
    elif scheme == "rtsps":
        default_port = 322
    else:
        default_port = 443
    port = parsed.port or default_port

    try:
        addrinfo = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addrinfo:
            return False, "dns_no_records"
    except OSError:
        return False, "dns_failed"

    try:
        with _connect_resolved(addrinfo, timeout, deadline) as sock:
            if scheme in {"https", "rtsps"}:
                try:
                    if isinstance(verify, str):
                        ca_option = "capath" if os.path.isdir(verify) else "cafile"
                        ctx = ssl.create_default_context(**{ca_option: verify})
                    else:
                        ctx = ssl.create_default_context()
                    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                    if verify is False:
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    sock.settimeout(_remaining_probe_timeout(timeout, deadline))
                    with ctx.wrap_socket(sock, server_hostname=host):
                        pass
                except OSError:
                    return False, "tls_failed"
    except OSError:
        return False, "tcp_failed"

    return True, "ok"


def _is_http_status_success(status: int) -> bool:
    return 200 <= status < 400


def _parse_416_total_length(content_range: str) -> int | None:
    # Example: "bytes */12345"
    m = re.search(r"bytes\s+\*/(\d+)", content_range or "", flags=re.IGNORECASE)
    if not m:
        return None
    try:
        val = int(m.group(1))
        return val if val > 0 else None
    except ValueError:
        return None


def _parse_suffix_range_bytes(range_header: str) -> int | None:
    # Example: "bytes=-2048"
    m = re.fullmatch(r"bytes=-(\d+)", (range_header or "").strip(), flags=re.IGNORECASE)
    if not m:
        return None
    try:
        val = int(m.group(1))
        return val if val > 0 else None
    except ValueError:
        return None


def _run_probe_request(
    url: str,
    request_kwargs: dict[str, Any],
    allow_redirects: bool,
    deadline: float | None = None,
) -> tuple[requests.Response, list[str]]:
    if allow_redirects:
        return _get_with_redirects(url, request_kwargs, deadline=deadline)
    request_kwargs = dict(request_kwargs)
    request_kwargs["timeout"] = _remaining_probe_timeout(
        request_kwargs["timeout"], deadline
    )
    resp = requests.get(url, **request_kwargs)
    chain: list[str] = []
    return resp, chain


def probe_url_with_range(
    url: str,
    *,
    timeout: float = 3,
    allow_redirects: bool = True,
    range_header: str = "bytes=0-1",
    headers: dict[str, str] | None = None,
    auth: Any = None,
    verify: bool | str | None = None,
    accept: str = DEFAULT_MEDIA_ACCEPT,
    use_conditional_cache: bool = True,
    probe_mp4_atoms: bool = True,
    preconnect: bool = False,
    preconnect_timeout: float = 2.0,
    range_retry_policy: str = "deterministic",
    allow_suffix_tail_fallback: bool = True,
) -> tuple[bool, dict[str, Any]]:
    """Probe ``url`` using a tiny ranged ``GET`` and return response metadata.

    This is more reliable than ``HEAD`` for many camera/server endpoints while
    still minimizing payload size. A media-biased ``Accept`` header is used
    by default to reduce HTML fallback responses from some origins/CDNs.
    When available, cached ``ETag`` / ``Last-Modified`` values are sent to
    prefer ``304 Not Modified`` responses on repeat checks.
    Optional DNS/TCP/TLS preconnect checks can short-circuit dead hosts.
    """

    deadline = time.monotonic() + timeout
    if preconnect:
        try:
            ok_pre, reason = _preconnect_check(
                url, timeout=min(timeout, preconnect_timeout), verify=verify
            )
        except (OSError, ValueError):
            ok_pre, reason = False, "preconnect_failed"
        if not ok_pre:
            return False, {"preconnect": reason, "ok": False}

    req_headers = dict(headers or {})
    if accept:
        req_headers.setdefault("Accept", accept)
    if use_conditional_cache:
        cached = _cache_get(url)
        if cached:
            etag = str(cached.get("etag") or "")
            last_modified = str(cached.get("last_modified") or "")
            if etag:
                req_headers.setdefault("If-None-Match", etag)
            if last_modified:
                req_headers.setdefault("If-Modified-Since", last_modified)
    if range_header:
        req_headers.setdefault("Range", range_header)

    request_kwargs: dict[str, Any] = {
        "timeout": timeout,
        "allow_redirects": allow_redirects,
        "headers": req_headers,
        "stream": True,
    }
    if auth is not None:
        request_kwargs["auth"] = auth
    if verify is not None:
        request_kwargs["verify"] = verify

    resp: requests.Response | None = None
    try:
        attempts: list[dict[str, Any]] = []

        def _attempt(
            label: str, headers: dict[str, str]
        ) -> tuple[requests.Response, list[str]]:
            local_kwargs = dict(request_kwargs)
            local_kwargs["headers"] = headers
            resp_i, chain_i = _run_probe_request(
                url, local_kwargs, allow_redirects, deadline=deadline
            )
            attempts.append(
                {"step": label, "status": int(getattr(resp_i, "status_code", 0) or 0)}
            )
            return resp_i, chain_i

        base_headers = dict(req_headers)
        had_range = "Range" in base_headers
        resp, chain = _attempt(
            "micro_range" if had_range else "micro_get", base_headers
        )
        suffix_total_len_hint = _parse_416_total_length(
            str(resp.headers.get("Content-Range") or "")
        )

        # Retry #2: plain micro-GET without Range if first attempt failed.
        if not _is_http_status_success(int(resp.status_code)) and had_range:
            resp.close()
            h2 = dict(base_headers)
            h2.pop("Range", None)
            resp, chain = _attempt("micro_get", h2)

        # Retry #3: suffix-range fallback to computed absolute tail range.
        if (
            not _is_http_status_success(int(resp.status_code))
            and range_retry_policy == "deterministic"
            and allow_suffix_tail_fallback
            and had_range
        ):
            suffix_len = _parse_suffix_range_bytes(str(base_headers.get("Range") or ""))
            total_len = _parse_416_total_length(
                str(resp.headers.get("Content-Range") or "")
            )
            if total_len is None:
                total_len = suffix_total_len_hint
            if suffix_len and total_len:
                resp.close()
                start = max(0, total_len - suffix_len)
                h3 = dict(base_headers)
                h3["Range"] = f"bytes={start}-{total_len - 1}"
                resp, chain = _attempt("computed_tail", h3)

        if len(chain) <= 1:
            history = [
                h.url for h in getattr(resp, "history", []) if getattr(h, "url", None)
            ]
            chain = history + ([resp.url] if getattr(resp, "url", None) else chain)

        etag = resp.headers.get("ETag", "")
        last_modified = resp.headers.get("Last-Modified", "")
        if use_conditional_cache and 200 <= int(resp.status_code) < 300:
            cache_key = str(getattr(resp, "url", url) or url)
            _cache_set(cache_key, etag=etag, last_modified=last_modified)
            if cache_key != url:
                _cache_set(url, etag=etag, last_modified=last_modified)

        content_type = resp.headers.get("Content-Type", "")
        content_range = resp.headers.get("Content-Range", "")
        info = {
            "status": resp.status_code,
            "probe_attempts": attempts,
            "content_type": content_type,
            "accept_ranges": resp.headers.get("Accept-Ranges", ""),
            "content_range": content_range,
            "etag": etag,
            "last_modified": last_modified,
            "url": getattr(resp, "url", url),
            "redirect_chain": chain,
            "ok": bool(resp.ok),
        }

        # All metadata above is detached from the response. Release its socket
        # before optional media requests so a small connection pool cannot stall.
        resp.close()
        resp = None
        if probe_mp4_atoms and info["ok"]:
            try:
                mp4_info = _probe_mp4_atoms(
                    url=url,
                    effective_url=str(info.get("url") or url),
                    content_type=content_type,
                    content_range=content_range,
                    timeout=timeout,
                    deadline=deadline,
                    allow_redirects=allow_redirects,
                    headers={
                        k: v for k, v in req_headers.items() if k.lower() != "range"
                    },
                    auth=auth,
                    verify=verify,
                )
            except (requests.RequestException, OSError, ValueError):
                # Optional metadata failures cannot erase proven HTTP reachability.
                mp4_info = {}
            if mp4_info:
                info["mp4_probe"] = mp4_info

        return True, info
    except Exception:
        return False, {}
    finally:
        # MP4 metadata and response parsing can fail after headers arrive.
        # Always release the streamed response, including those error paths.
        if resp is not None:
            resp.close()
