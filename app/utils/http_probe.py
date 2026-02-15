"""Small HTTP probe helpers used by connectivity/preflight checks."""

from __future__ import annotations

import re
import socket
import ssl
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_MEDIA_ACCEPT = "audio/*, application/octet-stream;q=0.9, */*;q=0.1"
PROBE_CACHE_TTL_SECONDS = 3600
MP4_PROBE_FRONT_BYTES = 128 * 1024
MP4_PROBE_TAIL_BYTES = 128 * 1024
MP4_MULTI_RANGE_MAX_BYTES = 384 * 1024

_probe_conditional_cache: dict[str, dict[str, Any]] = {}


def _cache_get(url: str) -> dict[str, Any] | None:
    entry = _probe_conditional_cache.get(url)
    if not entry:
        return None
    ts = float(entry.get("time") or 0)
    if ts <= 0 or time.time() - ts > PROBE_CACHE_TTL_SECONDS:
        _probe_conditional_cache.pop(url, None)
        return None
    return entry


def _cache_set(url: str, *, etag: str = "", last_modified: str = "") -> None:
    if not etag and not last_modified:
        return
    _probe_conditional_cache[url] = {
        "etag": etag,
        "last_modified": last_modified,
        "time": time.time(),
    }


def clear_probe_cache() -> None:
    """Clear in-memory conditional probe cache (tests/maintenance)."""

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


def _get_with_redirects(
    url: str,
    request_kwargs: dict[str, Any],
    max_redirects: int = 6,
) -> tuple[requests.Response, list[str]]:
    """Perform GET while preserving headers (including Range) across redirects."""

    current = url
    chain: list[str] = []
    last_resp: requests.Response | None = None

    for _ in range(max_redirects + 1):
        kwargs = dict(request_kwargs)
        kwargs["allow_redirects"] = False
        resp = requests.get(current, **kwargs)
        last_resp = resp

        effective = str(getattr(resp, "url", current) or current)
        chain.append(effective)
        status = int(getattr(resp, "status_code", 0) or 0)

        if status in {301, 302, 303, 307, 308}:
            location = str(resp.headers.get("Location") or "").strip()
            if not location:
                return resp, chain
            current = urljoin(effective, location)
            resp.close()
            continue

        return resp, chain

    if last_resp is None:
        raise requests.TooManyRedirects("redirect limit exceeded")
    return last_resp, chain


def _parse_multipart_byteranges(payload: bytes, content_type: str) -> dict[int, bytes]:
    """Parse ``multipart/byteranges`` payload into ``start->bytes`` map."""

    ct = content_type or ""
    m = re.search(r"boundary=([^;]+)", ct, flags=re.IGNORECASE)
    if not m:
        return {}
    boundary = m.group(1).strip().strip('"')
    if not boundary:
        return {}

    marker = ("--" + boundary).encode("latin-1", errors="ignore")
    parts = payload.split(marker)
    out: dict[int, bytes] = {}
    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue
        headers, sep, body = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        mcr = re.search(
            rb"Content-Range:\s*bytes\s+(\d+)-(\d+)/(\d+|\*)",
            headers,
            flags=re.IGNORECASE,
        )
        if not mcr:
            continue
        start = int(mcr.group(1))
        end = int(mcr.group(2))
        expected = max(0, end - start + 1)
        body = body.rstrip(b"\r\n")
        if expected and len(body) > expected:
            body = body[:expected]
        out[start] = body
    return out


def _fetch_sparse_multi_ranges(
    url: str,
    *,
    timeout: float,
    allow_redirects: bool,
    headers: dict[str, str],
    auth: Any,
    verify: bool | None,
    range_header: str,
) -> dict[int, bytes]:
    """Fetch sparse multi-range sample and parse multipart byte ranges."""

    h = dict(headers)
    h["Range"] = range_header
    kwargs: dict[str, Any] = {
        "timeout": timeout,
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
        if r.status_code != 206:
            return {}
        ct = str(r.headers.get("Content-Type", ""))
        if "multipart/byteranges" not in ct.lower():
            return {}

        buf = bytearray()
        for chunk in r.iter_content(chunk_size=8192):
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
    verify: bool | None,
    range_header: str,
) -> bytes:
    h = dict(headers)
    h["Range"] = range_header
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "allow_redirects": allow_redirects,
        "headers": h,
        "stream": True,
    }
    if auth is not None:
        kwargs["auth"] = auth
    if verify is not None:
        kwargs["verify"] = verify

    # Incremental parse path: read only the requested prefix bytes and stop.
    max_bytes = None
    m = range_header.strip().lower().removeprefix("bytes=")
    if "-" in m and "," not in m:
        start_s, end_s = m.split("-", 1)
        if start_s.isdigit() and end_s.isdigit():
            start = int(start_s)
            end = int(end_s)
            if end >= start:
                max_bytes = end - start + 1

    r = requests.get(url, **kwargs)
    try:
        if r.status_code >= 400:
            return b""
        buf = bytearray()
        for chunk in r.iter_content(chunk_size=4096):
            if not chunk:
                continue
            if max_bytes is not None and len(buf) + len(chunk) > max_bytes:
                take = max_bytes - len(buf)
                if take > 0:
                    buf.extend(chunk[:take])
                break
            buf.extend(chunk)
            if max_bytes is not None and len(buf) >= max_bytes:
                break
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
    verify: bool | None,
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
            range_header=sparse_header,
        )
        if parts:
            starts = sorted(parts.keys())
            front = parts.get(starts[0], b"")
            tail = parts.get(starts[-1], b"") if len(starts) > 1 else b""
            info["sparse_probe"] = "multi-range"

    if not front:
        front = _fetch_range_chunk(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            headers=headers,
            auth=auth,
            verify=verify,
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


def _preconnect_check(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Run DNS + TCP (and optional TLS) checks before HTTP probing."""

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False, "invalid_host"

    scheme = (parsed.scheme or "").lower()
    if scheme == "https":
        default_port = 443
    elif scheme == "http":
        default_port = 80
    elif scheme in {"rtsp", "rtsps"}:
        default_port = 554
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
        with socket.create_connection((host, port), timeout=timeout) as sock:
            if scheme == "https":
                try:
                    ctx = ssl.create_default_context()
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
) -> tuple[requests.Response, list[str]]:
    if allow_redirects:
        return _get_with_redirects(url, request_kwargs)
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
    verify: bool | None = None,
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

    if preconnect:
        ok_pre, reason = _preconnect_check(url, timeout=preconnect_timeout)
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

    try:
        attempts: list[dict[str, Any]] = []

        def _attempt(
            label: str, headers: dict[str, str]
        ) -> tuple[requests.Response, list[str]]:
            local_kwargs = dict(request_kwargs)
            local_kwargs["headers"] = headers
            resp_i, chain_i = _run_probe_request(url, local_kwargs, allow_redirects)
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
        if use_conditional_cache:
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

        if probe_mp4_atoms and bool(resp.ok):
            mp4_info = _probe_mp4_atoms(
                url=url,
                effective_url=str(info.get("url") or url),
                content_type=content_type,
                content_range=content_range,
                timeout=timeout,
                allow_redirects=allow_redirects,
                headers={k: v for k, v in req_headers.items() if k.lower() != "range"},
                auth=auth,
                verify=verify,
            )
            if mp4_info:
                info["mp4_probe"] = mp4_info

        resp.close()
        return True, info
    except Exception:
        return False, {}
