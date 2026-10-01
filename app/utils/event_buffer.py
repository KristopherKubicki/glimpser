"""Low-rate LAN camera event buffering.

This module keeps a small local ring of low-resolution frames for templates
that explicitly enable the LAN hardwired event-buffer profile. It is designed
for alert media, not archival recording.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

from app import config
from app.utils.template_manager import get_template
from app.utils.validators import event_buffer_eligibility, validate_template_name

EVENT_BUFFER_ROOT = Path(config.DATABASE_PATH).resolve().parent / "event_buffer"
_RESAMPLING = getattr(Image, "Resampling", Image)
_RUN_LOCK = threading.Lock()
_SESSION = requests.Session()
_MAX_HTTP_BYTES = 10 * 1024 * 1024
_EVENT_RETENTION_SECONDS = 24 * 60 * 60
_MAX_EVENT_FILES = 200
_FAILURES_BEFORE_BACKOFF = 3
_MIN_FAILURE_RETRY_SECONDS = 5
_MAX_FAILURE_RETRY_SECONDS = 30


@dataclass
class EventBufferState:
    next_due: float = 0.0
    backoff_until: float = 0.0
    failure_count: int = 0
    last_error: str = ""
    last_failure: float = 0.0
    last_success: float = 0.0


_STATE: dict[str, EventBufferState] = {}
_SNAPSHOT_RETRY: dict[str, float] = {}


def _finished_at(started_at: float, started_monotonic: float) -> float:
    return started_at + max(0.0, time.monotonic() - started_monotonic)


def _enabled_templates() -> dict[str, dict]:
    """Return raw template rows with event buffering explicitly enabled."""

    connection = None
    try:
        connection = sqlite3.connect(config.DATABASE_PATH, timeout=0.1)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM templates WHERE event_buffer_enabled = 1"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logging.debug("event buffer template lookup skipped: %s", exc)
        return {}
    finally:
        if connection is not None:
            connection.close()

    templates = {}
    for row in rows:
        name = str(row["name"] or "")
        if validate_template_name(name) is None:
            continue
        templates[name] = dict(row)
    return templates


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(default if value is None or value == "" else value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _safe_name(name: str) -> str:
    valid = validate_template_name(str(name))
    if valid is None:
        raise ValueError("invalid template name")
    return secure_filename(valid)


def _frame_dir(name: str) -> Path:
    return EVENT_BUFFER_ROOT / _safe_name(name) / "frames"


def _event_dir(name: str) -> Path:
    return EVENT_BUFFER_ROOT / _safe_name(name) / "events"


def _frame_timestamp(path: Path) -> float:
    try:
        return int(path.stem) / 1000.0
    except ValueError:
        return path.stat().st_mtime


def _template_ints(template: dict) -> dict[str, int]:
    fps = _bounded_int(template.get("event_buffer_fps"), 1, 1, 2)
    seconds = _bounded_int(template.get("event_buffer_seconds"), 120, 30, 300)
    width = _bounded_int(template.get("event_buffer_width"), 640, 320, 1280)
    pre_seconds = _bounded_int(template.get("event_buffer_pre_seconds"), 8, 0, 30)
    post_seconds = _bounded_int(template.get("event_buffer_post_seconds"), 6, 1, 30)
    backoff_seconds = _bounded_int(
        template.get("event_buffer_backoff_seconds"), 300, 30, 1800
    )
    if pre_seconds >= seconds:
        pre_seconds = max(seconds - 1, 0)
    if post_seconds > seconds:
        post_seconds = seconds
    return {
        "fps": fps,
        "seconds": seconds,
        "width": width,
        "pre_seconds": pre_seconds,
        "post_seconds": post_seconds,
        "backoff_seconds": backoff_seconds,
    }


def _failure_retry_seconds(template: dict, settings: dict[str, int]) -> int:
    timeout = _bounded_int(template.get("timeout"), 8, 2, 25)
    return min(
        settings["backoff_seconds"],
        max(_MIN_FAILURE_RETRY_SECONDS, min(timeout, _MAX_FAILURE_RETRY_SECONDS)),
    )


def _template_credentials(template: dict) -> tuple[str, str]:
    username = str(template.get("auth_username") or "")
    password = str(template.get("auth_password") or "")
    if not username or not password:
        parsed = urlparse(str(template.get("url") or ""))
        username = username or unquote(parsed.username or "")
        password = password or unquote(parsed.password or "")
    return username, password


def _auth_for_template(template: dict):
    username, password = _template_credentials(template)
    if username and password:
        return requests.auth.HTTPBasicAuth(username, password)
    return None


def _url_with_auth(url: str, template: dict) -> str:
    parsed = urlparse(url)
    if parsed.username or not template.get("auth_username"):
        return url
    username = quote(str(template.get("auth_username") or ""), safe="")
    password = quote(str(template.get("auth_password") or ""), safe="")
    if not username or not password or not parsed.hostname:
        return url
    netloc = f"{username}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _rtsp_event_url(url: str) -> str:
    """Prefer the low-resolution Hikvision substream for buffered RTSP frames."""

    parsed = urlparse(url)
    if parsed.scheme.lower() != "rtsp":
        return url
    path = parsed.path.replace("/Streaming/Channels/101", "/Streaming/Channels/102")
    path = path.replace("/streaming/channels/101", "/streaming/channels/102")
    if path == parsed.path:
        return url
    return urlunparse(parsed._replace(path=path))


def _lan_snapshot_template(template: dict) -> dict | None:
    """Use Hikvision's still endpoint only for standard-port private LAN RTSP."""
    parsed = urlparse(str(template.get("url") or ""))
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        if (
            not address.is_private
            or address.is_loopback
            or parsed.port not in (None, 554)
        ):
            return None
    except ValueError:
        return None
    match = re.fullmatch(r"/Streaming/Channels/(\d+)", parsed.path, re.I)
    if parsed.scheme != "rtsp" or not match:
        return None
    username, password = _template_credentials(template)
    host = f"[{address}]" if address.version == 6 else str(address)
    channel = match[1][:-1] + "2"
    return {
        **template,
        "url": f"http://{host}/ISAPI/Streaming/channels/{channel}/picture",
        "auth_username": username,
        "auth_password": password,
        "timeout": 3,
    }


def _capture_lan_frame(name: str, template: dict, timestamp: float, width: int) -> Path:
    """Prefer a cheap snapshot; back off unsupported endpoints before RTSP retry."""
    started = time.monotonic()
    snapshot = _lan_snapshot_template(template)
    if snapshot and time.monotonic() >= _SNAPSHOT_RETRY.get(name, 0):
        try:
            return _capture_http_frame(name, snapshot, timestamp, width)
        except (requests.RequestException, ValueError, OSError):
            # A failed snapshot must not disable an otherwise working RTSP feed.
            _SNAPSHOT_RETRY[name] = time.monotonic() + 300
    return _capture_rtsp_frame(name, template, _finished_at(timestamp, started), width)


def _prepare_image(image: Image.Image, width: int) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    if width and image.width > width:
        height = max(1, int(image.height * (width / image.width)))
        image = image.resize((width, height), _RESAMPLING.LANCZOS)
    return image


def _save_frame(name: str, image: Image.Image, timestamp: float, width: int) -> Path:
    frame_dir = _frame_dir(name)
    frame_dir.mkdir(parents=True, exist_ok=True)
    final_path = frame_dir / f"{int(timestamp * 1000)}.jpg"
    prepared = _prepare_image(image, width)
    tmp_path = None
    try:
        # Keep concurrent same-timestamp writers isolated on the destination
        # filesystem; publish only a completely encoded frame.
        with tempfile.NamedTemporaryFile(
            dir=frame_dir, suffix=".jpg.tmp", delete=False
        ) as handle:
            tmp_path = Path(handle.name)
        prepared.save(tmp_path, "JPEG", quality=72, optimize=True)
        os.replace(tmp_path, final_path)
        return final_path
    finally:
        prepared.close()
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _capture_http_frame(
    name: str, template: dict, timestamp: float, width: int
) -> Path:
    started = time.monotonic()
    url = str(template.get("url") or "").strip()
    timeout = _bounded_int(template.get("timeout"), 3, 2, 5)
    deadline = started + timeout

    def remaining_timeout() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise requests.Timeout("event buffer download deadline exceeded")
        return remaining

    def request(auth):
        return _SESSION.get(
            url,
            timeout=remaining_timeout(),
            verify=False,
            auth=auth,
            headers={"User-Agent": "GlimpserEventBuffer/1.0"},
            allow_redirects=True,
            stream=True,
        )

    from io import BytesIO

    with BytesIO() as payload:
        response = request(_auth_for_template(template))
        try:
            username, password = _template_credentials(template)
            if response.status_code == 401 and username and password:
                response.close()
                response = request(requests.auth.HTTPDigestAuth(username, password))
            response.raise_for_status()
            # Bound decoded bytes as they arrive; response.content would first
            # buffer an unbounded body, defeating the size check entirely.
            for chunk in response.iter_content(chunk_size=64 * 1024):
                remaining_timeout()
                if payload.tell() + len(chunk) > _MAX_HTTP_BYTES:
                    raise ValueError("event buffer frame too large")
                payload.write(chunk)
        finally:
            response.close()
        payload.seek(0)
        try:
            with Image.open(payload) as image:
                return _save_frame(name, image, _finished_at(timestamp, started), width)
        except UnidentifiedImageError as exc:
            raise ValueError("event buffer response is not an image") from exc


def _capture_rtsp_frame(
    name: str, template: dict, timestamp: float, width: int
) -> Path:
    started = time.monotonic()
    url = _rtsp_event_url(
        _url_with_auth(str(template.get("url") or "").strip(), template)
    )
    timeout = _bounded_int(template.get("timeout"), 12, 5, 25)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"glimpser_event_{_safe_name(name)}_", suffix=".jpg"
    )
    os.close(fd)
    try:
        command = [
            config.FFMPEG_PATH,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            url,
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "6",
            "-y",
            tmp_name,
        ]
        subprocess.run(command, timeout=timeout, check=True, capture_output=True)
        with Image.open(tmp_name) as image:
            return _save_frame(name, image, _finished_at(timestamp, started), width)
    finally:
        try:
            os.remove(tmp_name)
        except OSError:
            pass


def capture_event_frame(
    name: str, template: dict, timestamp: float | None = None
) -> Path:
    """Capture one low-resolution frame for an eligible LAN event buffer."""

    timestamp = time.time() if timestamp is None else timestamp
    eligible, reason = event_buffer_eligibility(template)
    if not eligible:
        raise ValueError(reason)
    settings = _template_ints(template)
    scheme = urlparse(str(template.get("url") or "")).scheme.lower()
    if scheme == "rtsp":
        frame = _capture_lan_frame(name, template, timestamp, settings["width"])
    else:
        frame = _capture_http_frame(name, template, timestamp, settings["width"])
    _prune_frames(name, settings["seconds"], settings["fps"])
    return frame


def _prune_frames(name: str, seconds: int, fps: int, now: float | None = None) -> None:
    now = time.time() if now is None else now
    frame_dir = _frame_dir(name)
    if not frame_dir.exists():
        return
    max_frames = max(10, int(seconds * fps) + 4)
    frames = sorted(frame_dir.glob("*.jpg"), key=_frame_timestamp)
    cutoff = now - seconds
    for frame in frames:
        if _frame_timestamp(frame) < cutoff:
            frame.unlink(missing_ok=True)
    frames = sorted(frame_dir.glob("*.jpg"), key=_frame_timestamp)
    for frame in frames[:-max_frames]:
        frame.unlink(missing_ok=True)


def _prune_events(name: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    event_dir = _event_dir(name)
    if not event_dir.exists():
        return
    retained = []
    for event in event_dir.glob("*.gif"):
        try:
            modified = event.stat().st_mtime
        except FileNotFoundError:
            # Other replay requests may prune the same directory concurrently.
            continue
        if now - modified > _EVENT_RETENTION_SECONDS:
            event.unlink(missing_ok=True)
        else:
            retained.append((modified, event))
    # Reuse this snapshot instead of re-listing/statting each surviving file.
    # Newly published clips will be considered by the next cleanup pass.
    retained.sort()
    for _, event in retained[:-_MAX_EVENT_FILES]:
        event.unlink(missing_ok=True)


def _capture_due_template(name, template, now):
    """Capture one due camera; each batch owns its camera states exclusively."""
    result = {"captured": 0, "backoff": 0, "failed": 0}
    settings = _template_ints(template)
    state = _STATE.setdefault(str(name), EventBufferState())
    if now < state.backoff_until:
        result["backoff"] += 1
        return result
    if now < state.next_due:
        return result
    state.next_due = now + (1.0 / max(settings["fps"], 1))
    started_monotonic = time.monotonic()
    try:
        capture_event_frame(str(name), template, now)
    except Exception as exc:
        finished_at = _finished_at(now, started_monotonic)
        state.failure_count += 1
        state.last_error = str(exc)[:200]
        state.last_failure = finished_at
        if state.failure_count >= _FAILURES_BEFORE_BACKOFF:
            state.backoff_until = finished_at + settings["backoff_seconds"]
            state.next_due = state.backoff_until
        else:
            # RTSP cameras can miss a keyframe window without being down.
            # Retry briefly before using the longer outage backoff.
            state.backoff_until = 0.0
            state.next_due = finished_at + _failure_retry_seconds(template, settings)
        result["failed"] += 1
        logging.info(
            "event buffer capture failed for %s (%s/%s): %s",
            name,
            state.failure_count,
            _FAILURES_BEFORE_BACKOFF,
            exc,
        )
        return result
    state.failure_count = 0
    state.last_error = ""
    state.last_failure = 0.0
    state.backoff_until = 0.0
    finished_at = _finished_at(now, started_monotonic)
    state.next_due = finished_at + (1.0 / max(settings["fps"], 1))
    state.last_success = finished_at
    result["captured"] += 1
    return result


def tick_event_buffers(now: float | None = None) -> dict[str, int]:
    """Capture due frames for all enabled LAN event buffers."""

    now = time.time() if now is None else now
    result = {"enabled": 0, "captured": 0, "backoff": 0, "blocked": 0, "failed": 0}
    if not _RUN_LOCK.acquire(blocking=False):
        result["blocked"] += 1
        return result
    try:
        templates = _enabled_templates()
        result["enabled"] = len(templates)
        batch_started = time.monotonic()

        def capture(item):
            name, template = item
            # Do not label later queued cameras with the first camera's time.
            started = _finished_at(now, batch_started)
            return _capture_due_template(name, template, started)

        # RTSP one-frame acquisition waits for keyframes. A bounded pool keeps
        # one slow camera from serializing every other buffer, without opening
        # an unbounded number of camera sessions or persistent encoders.
        with ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="event-frame"
        ) as pool:
            for captured in pool.map(capture, templates.items()):
                for key, count in captured.items():
                    result[key] += count
    finally:
        _RUN_LOCK.release()
    return result


def _frames_for_window(name: str, start: float, end: float) -> list[Path]:
    frame_dir = _frame_dir(name)
    if not frame_dir.exists():
        return []
    frames = sorted(frame_dir.glob("*.jpg"), key=_frame_timestamp)
    return [frame for frame in frames if start <= _frame_timestamp(frame) <= end]


def _sample_frames(frames: list[Path], max_frames: int = 60) -> list[Path]:
    if max_frames <= 0:
        return []
    if len(frames) <= max_frames:
        return frames
    if max_frames == 1:
        return frames[-1:]
    # Retain both ends so a sampled replay includes the newest captured action.
    step = (len(frames) - 1) / (max_frames - 1)
    return [frames[round(i * step)] for i in range(max_frames)]


def build_event_gif(
    name: str,
    event_time: float | None = None,
    wait_post: float | None = None,
) -> Path | None:
    """Build an alert GIF from buffered frames around *event_time*."""

    safe_name = _safe_name(name)
    template = get_template(safe_name)
    if not template:
        return None
    settings = _template_ints(template)
    event_time = time.time() if event_time is None else event_time
    wait = settings["post_seconds"] if wait_post is None else max(0.0, wait_post)
    deadline = event_time + min(wait, settings["post_seconds"], 10)
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(0.25, remaining))

    start = event_time - settings["pre_seconds"]
    end = event_time + settings["post_seconds"]
    frames = _frames_for_window(safe_name, start, end)
    frames = _sample_frames(frames)
    if not frames:
        return None

    event_dir = _event_dir(safe_name)
    event_dir.mkdir(parents=True, exist_ok=True)
    gif_path = event_dir / f"{safe_name}_{int(event_time * 1000)}.gif"
    with ExitStack() as resources:
        images, times = [], []
        for frame in frames:
            try:
                with Image.open(frame) as image:
                    converted = image.convert("RGB")
                    # Close decoded pixel storage even when encoding raises and
                    # an exception traceback retains this function's locals.
                    resources.callback(converted.close)
                    images.append(converted)
                    times.append(_frame_timestamp(frame))
            except (OSError, UnidentifiedImageError):
                continue
        if not images:
            return None

        # Acquisition can be slower than configured FPS, especially for RTSP.
        # Preserve elapsed time across dropped, sampled, or unreadable frames.
        durations = [
            max(100, round((end - start) * 100) * 10)
            for start, end in zip(times, times[1:])
        ]
        durations.append(max(250, int(1000 / max(settings["fps"], 1))))
        with tempfile.NamedTemporaryFile(
            dir=event_dir, suffix=".gif.tmp", delete=False
        ) as handle:
            tmp_path = Path(handle.name)
        try:
            images[0].save(
                tmp_path,
                format="GIF",
                save_all=True,
                append_images=images[1:],
                duration=durations,
                loop=0,
                optimize=True,
            )
            os.replace(tmp_path, gif_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        _prune_events(safe_name)
        return gif_path


def recent_replay(name: str, now: float | None = None) -> dict | None:
    """Build a short replay only from recent buffered frames, with honest timing.

    No camera capture is triggered. A stalled buffer or single still is not a
    motion clip. Durations follow acquisition times rather than configured FPS.
    """
    now = time.time() if now is None else now
    safe_name = _safe_name(name)
    template = get_template(safe_name)
    if not template or not template.get("event_buffer_enabled"):
        return None
    frames = _sample_frames(_frames_for_window(safe_name, now - 30, now), 30)
    with ExitStack() as resources:
        images, times, fingerprints = [], [], set()
        for frame in frames:
            try:
                with Image.open(frame) as image:
                    converted = image.convert("RGB")
                    # Close decoded pixel storage even when encoding raises and
                    # an exception traceback retains this function's locals.
                    resources.callback(converted.close)
                    images.append(converted)
                    times.append(_frame_timestamp(frame))
                    fingerprints.add(hashlib.sha256(images[-1].tobytes()).digest())
            except (OSError, UnidentifiedImageError):
                continue
        if (
            len(images) < 2
            or len(fingerprints) < 2
            or now - times[-1] > 15
            or times[-1] <= times[0]
        ):
            return None
        durations = [max(100, round((b - a) * 1000)) for a, b in zip(times, times[1:])]
        durations.append(durations[-1])
        directory = _event_dir(safe_name)
        directory.mkdir(parents=True, exist_ok=True)
        # Stable frame-derived filename makes repeated requests reusable. Each
        # writer has its own temporary path, so two kiosk requests cannot collide.
        path = directory / f"replay_{int(times[0] * 1000)}_{int(times[-1] * 1000)}.gif"
        if not path.exists():
            import tempfile

            with tempfile.NamedTemporaryFile(
                dir=directory, suffix=".gif.tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
            try:
                images[0].save(
                    temporary,
                    format="GIF",
                    save_all=True,
                    append_images=images[1:],
                    duration=durations,
                    optimize=True,
                )
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            _prune_events(safe_name)
        return {
            "path": path,
            "start": times[0],
            "end": times[-1],
            "frames": len(images),
            "fps": round((len(images) - 1) / (times[-1] - times[0]), 2),
        }


def event_buffer_status(name: str) -> dict[str, object]:
    """Return lightweight status for a template event buffer."""

    safe_name = _safe_name(name)
    frames = sorted(_frame_dir(safe_name).glob("*.jpg"), key=_frame_timestamp)
    state = _STATE.get(safe_name, EventBufferState())
    return {
        "frames": len(frames),
        "oldest": _frame_timestamp(frames[0]) if frames else None,
        "newest": _frame_timestamp(frames[-1]) if frames else None,
        "backoff_until": state.backoff_until or None,
        "failure_count": state.failure_count,
        "last_error": state.last_error,
        "last_failure": state.last_failure or None,
        "last_success": state.last_success or None,
        "retry_after_seconds": max(0, round(state.next_due - time.time())),
    }
