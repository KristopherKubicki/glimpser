# flake8: noqa
import csv
import email.utils
import fcntl
import glob
import hashlib
import inspect
import io
import json
import logging
import math
import os
import random
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import typing
import uuid
from collections import deque
from datetime import datetime, timedelta
from fractions import Fraction
from functools import lru_cache, wraps
from ipaddress import ip_address
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlparse

import psutil
import requests
from dateutil import tz
from flask import (
    Flask,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    stream_with_context,
    url_for,
)
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.http import http_date
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

logging.getLogger("werkzeug").setLevel(logging.WARNING)

import app.config as config
from app.config import (
    API_KEY,
    BACKUP_PATH,
    CHYRON_SPEED,
    CLIP_MODEL_NAME,
    CLIPS_DIRECTORY,
    CLOCK_DIGITAL,
    CLOCK_NAVBAR,
    CLOCK_OVERLAY,
    DOCS_DIRECTORY,
    HEALTH_STATUS_ALWAYS_VISIBLE,
    NAV_ICON,
    SCREENSHOT_DIRECTORY,
    SENSITIVE_SETTINGS,
    VERSION,
    VIDEO_DIRECTORY,
    backup_config,
    restore_config,
)
from app.models import PushSubscription, Summary, User
from app.utils import (
    camera_discovery,
    camera_fix,
    limit_rate,
    prompt_optimizer,
    scheduling,
    screenshots,
    template_manager,
    test_pattern,
    video_archiver,
)
from app.utils.llm import ask_question
from app.utils.screenshots import (
    capture_frame_from_stream,
    check_user_activity,
    is_chrome_debug_port_open,
)
from app.utils.settings_tooltips import (
    EMAIL_FIELDS,
    LOCKED_SETTINGS,
    NUMERIC_FIELDS,
    SETTINGS_CHOICES,
    SETTINGS_GROUPS,
    SETTINGS_PLACEHOLDERS,
    SETTINGS_TOOLTIPS,
)

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional dependency
    ort = None


@lru_cache(maxsize=1)
def clip_gpu_available() -> bool:
    """Return True when ONNXRuntime can use CUDA."""
    if ort is None:
        return False
    providers = getattr(ort, "get_available_providers", lambda: [])()
    return "CUDAExecutionProvider" in providers


# Names of settings that store file paths.
FILE_LOCATION_NAMES = [
    "DATABASE_PATH",
    "LOGGING_PATH",
    "BACKUP_PATH",
    "SCREENSHOT_DIRECTORY",
    "VIDEO_DIRECTORY",
    "SUMMARIES_DIRECTORY",
]

from typing import Any, Callable, Dict, Generator, List, Optional

from sqlalchemy.exc import OperationalError, SQLAlchemyError

import app.utils.media_utils as media_utils
from app.utils.db import SessionLocal, engine

# Clip caching constants
CACHE_TTL_SEC = 120
PNG_TTL_SEC = 1
SEGMENT_SEC = 10


FFMPEG = config.FFMPEG_PATH  # shortcut
# Limit configuration uploads to 5 MB to avoid excessive memory usage
MAX_UPLOAD_SIZE = 5 * 1024 * 1024

# Precompiled regular expression for validating filenames. Only letters,
# numbers, periods, hyphens and underscores are allowed. Using a compiled
# regex avoids recompiling the pattern on every call to ``allowed_filename``.
ALLOWED_FILENAME_RE = media_utils.ALLOWED_FILENAME_RE


# ---------- tiny helpers ----------------------------------------------------
@lru_cache(maxsize=256)
def _duration(p: str) -> float:
    """Wrapper for :func:`media_utils._duration`."""

    return media_utils._duration(p)


@lru_cache(maxsize=256)
def _probe(p: str, key: str):
    """Wrapper for :func:`media_utils._probe`."""

    return media_utils._probe(p, key)


def send_conditional_file(
    source: Path | str | io.BytesIO, cache_seconds: int = 0, mimetype: str | None = None
) -> Response:
    """Return a file or buffer with ETag and caching headers."""

    if isinstance(source, (str, os.PathLike)):
        if mimetype:
            resp = send_file(source, conditional=True, mimetype=mimetype)
        else:
            resp = send_file(source, conditional=True)
        stat = os.stat(source)
        mtime = int(stat.st_mtime)
        size = stat.st_size
    else:
        if mimetype:
            resp = send_file(
                source, conditional=True, mimetype=mimetype, download_name="buffer"
            )
        else:
            resp = send_file(source, conditional=True, download_name="buffer")
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(0)
        mtime = int(time.time())

    etag = f"{mtime}-{size}"
    resp.set_etag(etag)
    resp.headers["Cache-Control"] = f"public, max-age={cache_seconds}"
    resp.headers["Expires"] = http_date(time.time() + cache_seconds)
    resp.make_conditional(request)
    return resp


def _concat_copy(out: Path, parts: list[Path], clip_len: int = 120) -> bool:
    """Wrap :func:`media_utils._concat_copy` using local helpers."""

    # tests patch :func:`_duration` and :func:`_probe` on this module, so
    # temporarily override the utility's references with ours
    orig_duration = media_utils._duration
    orig_probe = media_utils._probe
    media_utils._duration = _duration
    media_utils._probe = _probe
    try:
        return media_utils._concat_copy(out, parts, clip_len)
    finally:
        media_utils._duration = orig_duration
        media_utils._probe = orig_probe


# ---------- main ------------------------------------------------------------

try:
    COMMIT_HASH = (
        subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
        .decode()
        .strip()
    )
except Exception:
    COMMIT_HASH = "unknown"
NODE_ENV = os.getenv("NODE_ENV", "development")

from app.utils import validators
from app.utils.email_alerts import send_email_alert
from app.utils.profiling import get_latency_stats, profile_route

# from app.models.log import Log
from app.utils.scheduling import log_cache, log_cache_lock
from app.utils.screenshots import (
    check_user_activity,
    get_chrome_path,
    get_chrome_version,
    is_chrome_debug_port_open,
    load_font,
)
from app.utils.sms_alerts import send_sms_alert
from app.utils.validators import (
    validate_setting,
    validate_template_name,
    validate_update_data,
)
from scripts.update_chrome_shortcut import (
    LINUX_PATHS,
    first_shortcut_path,
    shortcuts_need_patch,
    update_chrome_shortcuts_info,
)


def restart_server() -> None:
    """Restart the current Python process in a background thread."""

    logging.info("Restarting server...")

    def delayed_restart():
        time.sleep(1)  # 1-second delay
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Start the delayed restart in a daemon thread so the response returns
    restart_thread = Thread(target=delayed_restart, daemon=True)
    restart_thread.start()


class TemplateName:
    """Validated wrapper for template names.

    Ensures that only names passing ``validate_template_name`` are
    accepted when referencing templates in routes.
    """

    def __init__(self, name: str):
        if not self.validate(name):
            raise ValueError(f"Invalid template name: {name}")
        self._name = name

    @staticmethod
    def validate(name: str) -> bool:
        name = validate_template_name(name)
        if name is None:
            return False
        return True

    def __str__(self):
        return self._name

    def __repr__(self):
        return f"TemplateName({self._name!r})"


def generate_timed_hash():
    """Return a short‑lived hash derived from the API key.

    The resulting string combines a SHA-256 digest of the API key and an
    expiration timestamp. The timestamp is 15 minutes in the future, allowing
    the caller to generate a temporary token for secure, time limited access.
    """
    expiration_time = int(time.time()) + 15 * 60
    to_hash = f"{API_KEY}{expiration_time}"
    hash_digest = hashlib.sha256(to_hash.encode()).hexdigest()
    return f"{hash_digest}.{expiration_time}"


def is_hash_valid(timed_hash: str) -> bool:
    """Return ``True`` if ``timed_hash`` is valid and not expired."""
    try:
        hash_digest, expiration_time = timed_hash.split(".")
        to_hash = f"{API_KEY}{expiration_time}"
        valid_hash = hashlib.sha256(to_hash.encode()).hexdigest()
        if int(expiration_time) < int(time.time()):
            return False
        if valid_hash != hash_digest:
            return False
        return True
    except ValueError:
        # Incorrectly formatted hash
        return False


def is_safe_redirect_url(target: str | None) -> bool:
    """Return ``True`` when ``target`` is a safe relative URL."""

    if not target:
        return False
    if "\n" in target or "\r" in target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def login_required(f: Callable) -> Callable:
    """Decorator enforcing session or API key authentication for routes."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow LAN access without login when configured
        ip = request.remote_addr
        try:
            ip_obj = ip_address(ip) if ip else None
        except ValueError:
            ip_obj = None
        if (
            ip_obj
            and any(ip_obj in net for net in config.SKIP_LOGIN_SUBNETS)
            and not request.path.startswith("/settings")
        ):
            return f(*args, **kwargs)
        # Check for API key in headers, GET parameters, or POST form data
        api_key = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
            or request.form.get("api_key")
        )
        timed_key = request.args.get("timed_key")

        # Check for valid timed API key
        if timed_key:
            if not is_hash_valid(timed_key):
                logging.warning("Invalid timed key from %s", ip)
                return jsonify({"error": "Invalid timed key"}), 401
            return f(*args, **kwargs)

        # Check for valid static API key
        elif api_key == API_KEY:
            return f(*args, **kwargs)

        # Check for valid session
        elif session.get("user_id"):
            # Ensure the stored user_id is an integer. Any malformed session
            # data should trigger a logout redirect rather than allowing the
            # request through.
            if not isinstance(session.get("user_id"), int):
                logging.warning("Malformed session for %s", ip)
                session.pop("user_id", None)
                if current_app.secret_key:
                    flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))

            expiry = session.get("expiry")
            if expiry and datetime.now() > datetime.strptime(
                expiry, "%Y-%m-%d %H:%M:%S"
            ):
                logging.info(
                    "Expired session for user %s from %s",
                    session.get("user_id"),
                    ip,
                )
                session.pop("user_id", None)
                if current_app.secret_key:
                    flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))

            # Refresh expiry so the timeout is based on inactivity
            timeout = (
                timedelta(days=config.AUTO_LOGIN_DAYS)
                if session.get("remember")
                else timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)
            )
            session["expiry"] = (datetime.now() + timeout).strftime("%Y-%m-%d %H:%M:%S")

            db_session = SessionLocal()
            try:
                inspector = sa_inspect(engine)
                if "users" in inspector.get_table_names():
                    user = (
                        db_session.query(User).filter_by(id=session["user_id"]).first()
                    )
                else:
                    user = {"id": session["user_id"]}
            finally:
                db_session.close()

            if not user:
                logging.info(
                    "Session user id %s not found for %s",
                    session.get("user_id"),
                    ip,
                )
                session.pop("user_id", None)
                if current_app.secret_key:
                    flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))

            # Optional role checks could be added here
            return f(*args, **kwargs)

        # Handle missing or invalid authentication
        else:
            if api_key:
                logging.warning("Invalid API key from %s", ip)
                return jsonify({"error": "Invalid API key"}), 401
            else:
                # For Server-Sent Events endpoints, return an SSE-formatted
                # authentication error so the client can handle it without
                # interpreting an HTML login page. This avoids the browser
                # warning: "EventSource's response has a MIME type
                # ('text/html') that is not 'text/event-stream'."
                if "text/event-stream" in request.headers.get("Accept", ""):
                    message = 'data: {"error": "unauthorized"}\n\n'
                    return Response(message, status=401, mimetype="text/event-stream")

                # When no session cookie is present the user might have cookies
                # disabled or the SESSION_COOKIE_SECURE flag could block the
                # cookie over HTTP. Provide a hint and log for easier debugging
                if "session" not in request.cookies:
                    if current_app.secret_key:
                        flash(
                            "Login requires cookies. Check browser settings.",
                            "error",
                        )
                    logging.debug("Missing session cookie from %s", request.remote_addr)
                else:
                    logging.debug("No valid auth cookie from %s", ip)
                return redirect(url_for("login", next=request.url))

    return decorated_function


# Function to read logs from the local text file and filter them based on query parameters
def read_logs_from_memory(
    level: Optional[str] = None,
    source: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return in-memory logs filtered by the given criteria."""

    # global log_cache

    filtered_logs = []
    with log_cache_lock:
        for log in log_cache:
            # Apply filters if specified
            if (level and log["level"] != level) or (
                source and log["source"] != source
            ):
                continue
            if start_date and log["timestamp"] < datetime.fromisoformat(start_date):
                continue
            if end_date and log["timestamp"] > datetime.fromisoformat(end_date):
                continue
            if search and search.lower() not in log["message"].lower():
                continue

            filtered_logs.append(log)

    # Return logs sorted by timestamp in descending order
    return sorted(filtered_logs, key=lambda x: x["timestamp"], reverse=True)


def get_all_settings() -> List[Dict[str, Any]]:
    """Return all configuration settings from the database and defaults."""

    session = SessionLocal()
    try:
        # Fetch all settings from the database
        try:
            db_rows = session.execute(
                text("SELECT name, value FROM settings")
            ).fetchall()
            db_settings = {row[0]: row[1] for row in db_rows}
        except (OperationalError, sqlite3.OperationalError) as e:
            if "no such table" in str(e):
                # This is expected for a fresh database during initial setup.
                logging.warning("table does not exist")
            else:
                logging.warning("database error %s", e)
            db_settings = {}

        # Fetch all settings from config.py that use get_setting()
        settings = {}
        for name, value in inspect.getmembers(config):
            if inspect.isfunction(value):
                continue  # Skip functions
            if name.startswith("_"):
                continue

            if isinstance(value, (str, int, float, bool)):
                settings[name] = db_settings.get(name, value)

        # Include settings that are only in the database but not in config.py
        for name in db_settings:
            if name not in settings:
                settings[name] = db_settings[name]

        # Convert the dictionary to a list of dictionaries for easy template usage
        settings_list = [
            {"name": name, "value": value} for name, value in settings.items()
        ]

        # Remove sensitive items before showing them in the settings page
        lsettings_list = []
        for sl in settings_list:
            if (
                re.findall(r"^[A-Z_]+?$", sl["name"])
                and sl["name"] not in SENSITIVE_SETTINGS
            ):
                value = sl["value"]
                if isinstance(value, str) and validators.is_bool_string(value):
                    value = (
                        "True"
                        if value.strip().lower() in {"true", "on", "yes", "y", "t"}
                        else "False"
                    )
                lsettings_list.append({"name": sl["name"], "value": value})
        return lsettings_list
    finally:
        session.close()


def file_location_metrics(
    settings_list: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Return existence and disk free percent for file location settings."""

    metrics = {}
    for item in settings_list:
        path = os.path.expanduser(os.path.expandvars(str(item["value"])))
        exists = os.path.exists(path)
        free_pct = None
        if exists:
            try:
                # psutil.disk_usage works for both files and directories. If
                # the path is a file that doesn't exist yet, fall back to its
                # parent directory so we can still report disk capacity.
                target = path if os.path.isdir(path) else os.path.dirname(path)
                usage = psutil.disk_usage(target)
                free_pct = round(100 * usage.free / usage.total, 1)
            except Exception:
                free_pct = None
        metrics[item["name"]] = {"exists": exists, "free_pct": free_pct}

    return metrics


def update_setting(name: str, value: str, restart: bool = True) -> bool:
    """Persist a configuration ``name`` and ``value`` to the database.

    Parameters
    ----------
    name : str
        Setting name.
    value : str
        New setting value.
    restart : bool, optional
        Restart the server after updating the setting. Defaults to ``True``.
    """

    name = name.replace("'", "")[:32]
    value = value.replace("'", "")[:1024]

    if not re.findall(r"^[A-Z_]+?$", name):
        return False

    session = SessionLocal()
    delta = False
    try:
        existing_setting = session.execute(
            text("SELECT value FROM settings WHERE name = :name"),
            {"name": name},
        ).fetchone()
        if existing_setting:
            if existing_setting[0] != value:
                session.execute(
                    text("UPDATE settings SET value = :value WHERE name = :name"),
                    {"name": name, "value": value},
                )
                delta = True
                logging.debug("UPDATE %s %s %s", name, value, existing_setting)
        else:
            session.execute(
                text("INSERT INTO settings (name, value) VALUES (:name, :value)"),
                {"name": name, "value": value},
            )
            delta = True
        session.commit()
    except (OperationalError, sqlite3.OperationalError) as e:
        if "no such table" in str(e):
            logging.warning("settings table does not exist")
        else:
            logging.warning("database error %s", e)
        session.rollback()
    except SQLAlchemyError as e:  # pragma: no cover - unexpected errors
        logging.warning("database error %s", e)
        session.rollback()
    finally:
        session.close()

    if delta is True and restart:
        # Trigger server restart
        # is there a way to do this on a delay?
        restart_server()

    return True


def generate_video_stream(
    video_path: str, *, reopen_delay: float = 0.1
) -> Generator[bytes, None, None]:
    """Yield video data from ``video_path`` in chunks indefinitely.

    Parameters
    ----------
    video_path : str
        Path to the video file to stream.
    reopen_delay : float, optional
        Time to wait after reaching the end of the file before reopening it.
        This prevents tight loops from consuming CPU when the file ends.
        Defaults to ``0.1`` seconds.
    """

    # The video preview on the UI expects an infinite generator. Read the
    # file in 1MB increments and loop back to the beginning once no more
    # bytes are available.

    chunk_size = 1024 * 1024  # 1 MB
    while True:
        if not os.path.exists(video_path):
            logging.warning("Video path does not exist: %s", video_path)
            break

        with open(video_path, "rb") as video:
            while True:
                chunk = video.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        # Immediately loop back and stream again so the client sees a
        # seamless loop without gaps.
        time.sleep(reopen_delay)
        logging.debug("Restarting video stream")


def check_url_accessible(url: str) -> bool:
    """Return ``True`` if the URL responds to a HEAD request."""
    try:
        resp = requests.head(url, timeout=5)
        return resp.ok
    except Exception as exc:  # pragma: no cover
        logging.error("Connectivity check failed for %s: %s", url, exc)
        return False


def parse_cache_delay(headers: typing.Mapping[str, str]) -> float:
    """Return the time-to-live from HTTP cache headers."""

    cc = headers.get("Cache-Control", "")
    m = re.search(r"max-age=(\d+)", cc)
    if m:
        try:
            return float(m.group(1))
        except ValueError as exc:
            logging.warning("Invalid max-age header %s: %s", m.group(1), exc)
    expires = headers.get("Expires")
    if expires:
        try:
            dt = email.utils.parsedate_to_datetime(expires)
            return max(0.0, dt.timestamp() - time.time())
        except (TypeError, ValueError) as exc:
            logging.warning("Invalid Expires header %s: %s", expires, exc)
    return 0.0


def generate_live_stream(url: str) -> Generator[bytes, None, None]:
    """Yield video data directly from a remote URL using ``ffmpeg``.

    Some camera APIs expose JPEG snapshots rather than a continuous video
    stream. If the URL resembles a static image endpoint, poll the image
    directly to keep the live view working. Otherwise continuously invoke
    ``ffmpeg`` and restart it on failure so the client receives a valid
    MP4 stream whenever possible.
    """

    image_like = (
        url.lower().endswith((".jpg", ".jpeg", ".png")) or "/picture" in url.lower()
    )
    if image_like:
        session = screenshots.http_session()
        failures = 0
        base_delay = 1 / max(config.LIVE_FALLBACK_FPS, 1)
        last_hash = b""

        while True:
            try:
                resp = session.get(url, timeout=5, stream=True)
                if resp.status_code == 200:
                    data = resp.content
                    digest = hashlib.sha256(data).digest()
                    unchanged = digest == last_hash
                    last_hash = digest
                    yield data
                    if unchanged:
                        failures = min(failures + 1, 5)
                    else:
                        failures = 0
                    delay = max(base_delay, parse_cache_delay(resp.headers))
                else:
                    logging.error(
                        "Failed to fetch image from %s (HTTP %s)",
                        url,
                        resp.status_code,
                    )
                    failures += 1
                    delay = base_delay * (2**failures)
            except GeneratorExit:
                break
            except Exception as e:
                logging.error("Error fetching image from %s: %s", url, e)
                failures += 1
                delay = base_delay * (2**failures)

            time.sleep(min(delay, config.LIVE_MAX_RETRY_DELAY))
        return

    command = [config.FFMPEG_PATH]
    if config.FFMPEG_HWACCEL and config.FFMPEG_HWACCEL.lower() != "false":
        command.extend(["-hwaccel", config.FFMPEG_HWACCEL])

    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        command.extend(["-headers", f"User-Agent: {config.UA}\r\n"])
        command.extend(["-headers", f"referer: {base_url}\r\n"])
        command.extend(["-headers", f"origin: {base_url}\r\n"])
        command.extend(["-seekable", "0"])
    command.extend(
        [
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "2",
            "-i",
            url,
            "-loglevel",
            "error",
            "-an",
            "-c:v",
            "copy",
            "-f",
            "mp4",
            "-movflags",
            "frag_keyframe+empty_moov",
            "pipe:1",
        ]
    )

    failures = 0
    last_log = 0.0
    while True:
        if parsed.scheme in ("http", "https") and not check_url_accessible(url):
            failures += 1
            delay = 2 if failures == 0 else min(2**failures, 30)
            time.sleep(delay)
            continue

        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            chunk_yielded = False

            try:
                while True:
                    try:
                        chunk = process.stdout.read(1024 * 1024)
                    except BrokenPipeError:
                        raise GeneratorExit
                    if not chunk:
                        break
                    yield chunk
                    chunk_yielded = True
                    if process.poll() is not None:
                        break
            except GeneratorExit:
                if process:
                    process.kill()
                    process.wait(timeout=1)
                return
            finally:
                if process:
                    process.kill()
                    process.wait(timeout=1)
        except GeneratorExit:
            if process:
                process.kill()
                process.wait(timeout=1)
            return

        if process.returncode == 0:
            return

        now = time.time()
        if not chunk_yielded:
            failures += 1
            if failures >= config.LIVE_MAX_FAILURES:
                logging.error(
                    "ffmpeg failed %s times without output, giving up",
                    failures,
                )
                return
            if now - last_log > 10:
                logging.warning(
                    "ffmpeg exited with %s, retrying (%s/%s)",
                    process.returncode,
                    failures,
                    config.LIVE_MAX_FAILURES,
                )
                last_log = now
        else:
            failures = 0
            if now - last_log > 10:
                logging.warning("ffmpeg exited with %s, retrying", process.returncode)
                last_log = now

        # Exponential backoff keeps the server from hammering the camera URL
        # when ffmpeg repeatedly fails. The delay tops out at 30 seconds.
        delay = 2 if failures == 0 else min(2**failures, 30)
        time.sleep(delay)


login_attempts = {}
last_shot = None
last_time = None
active_groups = []
rtsp_sessions = {}
active_log_streams: dict[tuple[int, str, str], bool] = {}


def get_active_groups() -> List[str]:
    """Return a sorted list of all active group names."""
    global active_groups
    templates = template_manager.get_templates()
    active_cameras = []
    for id, template in templates.items():
        name = template.get("name")
        if name is None:
            continue

        lgroups = template.get("groups", "").strip().split(",")
        for lg in lgroups:
            active_cameras.append(lg.strip())
    active_cameras = sorted(list(set(active_cameras)))
    if "" in active_cameras:
        active_cameras.remove("")
    active_groups = active_cameras.copy()

    return active_cameras


def resize_and_pad(
    img: Image.Image,
    size: tuple[int, int],
    color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Resize ``img`` to fit ``size`` while preserving aspect ratio."""

    # Calculate the scaling factor to resize the image while maintaining the aspect ratio
    scale = max(size[0] / img.size[0], size[1] / img.size[1])

    # Resize the image using the scaling factor
    new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
    img = img.resize(new_size)

    # Create a new image with the specified size and color
    background = Image.new("RGB", size, color)

    # Paste the resized image onto the center of the background
    x = (size[0] - new_size[0]) // 2
    y = (size[1] - new_size[1]) // 2
    background.paste(img, (x, y))

    return background


def _placeholder_screenshot() -> io.BytesIO:
    """Return a simple PNG stating that no screenshot is available."""

    text = "No screenshot available"
    img = Image.new("RGB", (320, 240), "black")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((320 - w) / 2, (240 - h) / 2), text, fill="white", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _overlay_stream_timestamp(frame: bytes) -> bytes:
    """Return ``frame`` with a live timestamp overlay."""
    try:
        with Image.open(io.BytesIO(frame)) as img:
            img = img.convert("RGB")
            draw = ImageDraw.Draw(img)
            zone = tz.gettz(config.TZ) or tz.UTC
            timestamp = datetime.now(zone).strftime("%H:%M:%S")
            text = f"\u25cf {timestamp}"
            font_size = max(10, int(img.height * 0.03))
            font = load_font(font_size)
            padding = 4
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = img.width - text_w - padding
            y = img.height - int(font_size * 3.5)
            background = Image.new(
                "RGBA",
                (text_w + padding * 2, text_h + padding * 2),
                (0, 0, 0, 128),
            )
            img.paste(background, (x - padding, y - padding), background)
            draw.text(
                (x, y),
                text,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
            )
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()
    except Exception as exc:  # pragma: no cover - overlay failures are noncritical
        logging.debug("Stream timestamp overlay failed: %s", exc)
        return frame


lock = Lock()


def generate(
    group: Optional[str] = None,
    camera: Optional[str] = None,
    filename: str = "latest_camera.png",
    rtsp: bool = False,
    session_id: Optional[str] = None,
) -> Generator[bytes, None, None]:
    """Yield MJPEG or RTP frames from the latest screenshot files."""

    placeholder_jpeg: Optional[bytes] = None

    def _placeholder_frame() -> bytes:
        nonlocal placeholder_jpeg
        if placeholder_jpeg is None:
            buf = _placeholder_screenshot()
            with Image.open(buf) as img:
                img = resize_and_pad(img, (1280, 720))
                tmp = io.BytesIO()
                img.save(tmp, format="JPEG")
                placeholder_jpeg = tmp.getvalue()
        return placeholder_jpeg

    # Treat explicit "all" values as no filter
    if group == "all":
        group = None
    if camera == "all":
        camera = None

    # pretty hacky but it works ok
    global last_time, last_shot
    boundary = b"frame"
    while True:
        ltime = time.time()
        last_path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            SCREENSHOT_DIRECTORY,
            filename,
        ).replace(".png", ".jpg")

        frame = None
        if (
            os.path.exists(last_path)
            and os.path.getsize(last_path) > 0
            and os.path.getctime(last_path) > time.time() - 1
        ):
            # just read this image instead...
            with open(last_path, "rb") as f:
                frame = f.read()
        else:
            with lock:
                if (
                    group is None
                    and camera is None
                    and last_time
                    and time.time() - last_time < 1
                    and last_shot
                    and os.path.exists(last_shot)
                ):
                    # Serve the previously captured screenshot if a new frame
                    # was not generated. If the cached image cannot be opened,
                    # remove it and fall back to searching for a new screenshot.
                    try:
                        if screenshots._is_valid_png(last_shot):
                            with Image.open(last_shot) as img:
                                img = resize_and_pad(img, (1280, 720))
                                buffer = io.BytesIO()
                                img.save(buffer, format="JPEG")
                                frame = buffer.getvalue()
                        else:
                            logging.error(
                                "Failed to open last shot %s: invalid image",
                                last_shot,
                            )
                            try:
                                os.remove(last_shot)
                            except OSError as exc:
                                logging.warning(
                                    "Failed to remove bad shot %s: %s",
                                    last_shot,
                                    exc,
                                )
                            last_shot = None
                    except Exception as e:
                        logging.error("Failed to open last shot %s: %s", last_shot, e)
                        try:
                            os.remove(last_shot)
                        except OSError as exc:
                            logging.warning(
                                "Failed to remove bad shot %s: %s",
                                last_shot,
                                exc,
                            )
                        last_shot = None

                if frame is None:
                    # Replace this with your actual template manager code
                    templates = template_manager.get_templates()

                    # sorted_templates = sorted(templates.items(), key=lambda x: int(x[1].get('last_video_time', 0) or 0), reverse=True)
                    sorted_templates = (
                        templates.items()
                    )  # there is a problem with the sort..

                    most_recent_time = 0
                    most_recent_file = None
                    # there is some kind of bug in here where we will sometimes pick an image before we should (like if its not captioned yet)
                    for template_id, template_details in sorted_templates:
                        template_name = validate_template_name(
                            template_details.get("name")
                        )
                        if template_name is None:
                            continue

                        if camera and template_name != camera:
                            continue

                        template_groups = []
                        if group and "groups" in template_details:
                            template_groups = [
                                g.strip() for g in template_details["groups"].split(",")
                            ]
                            if group not in template_groups:
                                continue
                        elif group:
                            continue

                        path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            "..",
                            SCREENSHOT_DIRECTORY,
                            template_name,
                        )
                        # no need to loop through the directory if we find the symlink file
                        lfiles = []
                        file_path = os.path.join(path, filename)
                        if os.path.exists(file_path):
                            lfiles = [file_path]
                        else:
                            # fall back to the oldest screenshot so the MJPEG
                            # stream always has an initial frame
                            pngs = [
                                os.path.join(path, f)
                                for f in os.listdir(path)
                                if f.endswith(".png")
                                and os.path.isfile(os.path.join(path, f))
                            ]
                            if pngs:
                                pngs.sort(key=os.path.getctime)
                                lfiles = [pngs[0]]

                        last_file = lfiles[-1] if lfiles else None
                        if (
                            last_file
                            and os.path.exists(last_file)
                            and (
                                os.path.getmtime(last_file) > most_recent_time
                                or most_recent_file is None
                            )
                        ):
                            most_recent_file = last_file
                            most_recent_time = os.path.getmtime(last_file)

                    frame = None
                    if most_recent_file:
                        last_time = time.time()
                        last_shot = most_recent_file

                        try:
                            if screenshots._is_valid_png(most_recent_file):
                                with Image.open(most_recent_file) as img:
                                    img = resize_and_pad(img, (1280, 720))
                                    buffer = io.BytesIO()
                                    img.save(buffer, format="JPEG")
                                    frame = buffer.getvalue()
                            else:
                                logging.error(
                                    "Failed to open last shot %s: invalid image",
                                    most_recent_file,
                                )
                                try:
                                    os.remove(most_recent_file)
                                except OSError as exc:
                                    logging.warning(
                                        "Failed to remove invalid screenshot %s: %s",
                                        most_recent_file,
                                        exc,
                                    )
                                frame = None

                            if frame is not None:
                                # file sizes the same size?  maybe just touch the file instead?

                                # Write to a temporary file first, then atomically
                                # replace the cached JPEG. This avoids serving
                                # partially written files when new screenshots
                                # are generated.
                                temp_path = last_path + ".tmp"
                                with open(temp_path, "wb") as f:
                                    f.write(frame)
                                # Atomically move the temp file into place
                                os.replace(temp_path, last_path)
                        except Exception as exc:
                            logging.error(
                                "Failed to update screenshot cache: %s",
                                exc,
                                exc_info=True,
                            )
                            try:
                                os.remove(most_recent_file)
                            except OSError as remove_exc:
                                logging.warning(
                                    "Failed to remove invalid screenshot %s: %s",
                                    most_recent_file,
                                    remove_exc,
                                )

        if not frame:
            frame = _placeholder_frame()
        if frame:
            frame = _overlay_stream_timestamp(frame)
            if rtsp:
                if session_id and session_id in rtsp_sessions:
                    session = rtsp_sessions[session_id]
                    seq = session.get("seq", 0)
                    timestamp = session.get("timestamp", 0)
                    ssrc = session.get("ssrc", 0)
                    rtp_header = struct.pack("!BBHII", 0x80, 96, seq, timestamp, ssrc)
                    session["seq"] = (seq + 1) % 65536
                    session["timestamp"] = (timestamp + 3600) % 0x100000000
                else:
                    rtp_header = b"\x80\x60\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
                yield rtp_header + frame
            else:
                yield b"--" + boundary + b"\r\n"
                yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n"
        if time.time() - ltime > 1:
            continue
        time.sleep(1 - (time.time() - ltime))


def generate_fast_mjpg(camera: str) -> Generator[bytes, None, None]:
    """Yield MJPEG frames by repeatedly capturing screenshots.

    The function calls ``scheduling.update_camera`` directly to grab a fresh
    frame as quickly as possible. If capturing fails, the previously captured
    frame is re-used and the delay between attempts increases to avoid
    overwhelming the camera endpoint.
    """

    template = template_manager.get_template(camera)
    if not template:
        return

    boundary = b"frame"
    last_frame = None
    failures = 0

    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        SCREENSHOT_DIRECTORY,
        camera,
        "latest_camera.png",
    )

    while True:
        start = time.time()
        try:
            scheduling.update_camera(camera, template)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    last_frame = f.read()
            failures = 0
        except Exception as e:  # pragma: no cover - unexpected errors
            logging.error("fast mjpg capture failed for %s: %s", camera, e)
            failures += 1

        if last_frame:
            yield b"--" + boundary + b"\r\n"
            yield b"Content-Type: image/png\r\n\r\n" + last_frame + b"\r\n"

        delay = min(0.1 * (2**failures), 5)
        elapsed = time.time() - start
        if elapsed < delay:
            time.sleep(delay - elapsed)


def generate_caption_loop(
    *, group: Optional[str] = None, camera: Optional[str] = None
) -> Generator[bytes, None, None]:
    """Yield MJPEG frames showing the most recent caption.

    When ``camera`` or ``group`` is provided, the generator filters templates
    to those sources before selecting the newest caption. This mirrors the
    behavior of ``/stream.png`` and other endpoints.
    """

    boundary = b"frame"
    if group == "all":
        group = None
    if camera == "all":
        camera = None
    while True:
        caption = "No captions available"
        templates = template_manager.get_templates()
        newest_time = None
        for name, tpl in templates.items():
            if camera and name != camera:
                continue
            if group:
                if group not in [g.strip() for g in tpl.get("groups", "").split(",")]:
                    continue
            ts_str = tpl.get("last_caption_time")
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S") if ts_str else None
            except Exception:
                ts = None
            if ts and (newest_time is None or ts > newest_time):
                newest_time = ts
                caption = tpl.get("last_caption", "") or "No captions available"

        img = Image.new("RGB", (1280, 720), "black")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        wrapped = textwrap.fill(caption, width=60)
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((1280 - w) / 2, (720 - h) / 2), wrapped, fill="white", font=font)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        frame = buf.getvalue()

        yield b"--" + boundary + b"\r\n"
        yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(5)


def allowed_filename(filename: str) -> bool:
    """Wrapper for :func:`media_utils.allowed_filename`."""

    return media_utils.allowed_filename(filename)


def init_routes(app: Flask) -> None:
    """Register all route handlers on the given ``app``."""
    from app.blueprints.api import create_blueprint as create_api_blueprint
    from app.blueprints.assets import create_blueprint as create_assets_blueprint
    from app.blueprints.authentication import create_blueprint as create_auth_blueprint
    from app.blueprints.discovery import create_blueprint as create_discovery_blueprint
    from app.blueprints.docs import create_blueprint as create_docs_blueprint
    from app.blueprints.mcp import create_blueprint as create_mcp_blueprint
    from app.blueprints.media import create_blueprint as create_media_blueprint
    from app.blueprints.network import create_blueprint
    from app.blueprints.notifications import (
        create_blueprint as create_notifications_blueprint,
    )
    from app.blueprints.status import create_blueprint as create_status_blueprint
    from app.blueprints.stream import create_blueprint as create_stream_blueprint
    from app.blueprints.system import create_blueprint as create_system_blueprint
    from app.blueprints.timeline import create_blueprint as create_timeline_blueprint
    from app.blueprints.views import create_blueprint as create_views_blueprint

    if not getattr(app, "_network_bp_registered", False):
        app.register_blueprint(create_blueprint())
        app._network_bp_registered = True

    if not getattr(app, "_status_bp_registered", False):
        app.register_blueprint(create_status_blueprint())
        app._status_bp_registered = True

    if not getattr(app, "_notifications_bp_registered", False):
        app.register_blueprint(create_notifications_blueprint())
        app._notifications_bp_registered = True

    if not getattr(app, "_docs_bp_registered", False):
        app.register_blueprint(create_docs_blueprint())
        app._docs_bp_registered = True

    if not getattr(app, "_stream_bp_registered", False):
        app.register_blueprint(create_stream_blueprint())
        app._stream_bp_registered = True

    if not getattr(app, "_media_bp_registered", False):
        app.register_blueprint(create_media_blueprint())
        app._media_bp_registered = True

    if not getattr(app, "_assets_bp_registered", False):
        app.register_blueprint(create_assets_blueprint())
        app._assets_bp_registered = True

    if not getattr(app, "_system_bp_registered", False):
        app.register_blueprint(create_system_blueprint())
        app._system_bp_registered = True

    if not getattr(app, "_api_bp_registered", False):
        app.register_blueprint(create_api_blueprint())
        app._api_bp_registered = True

    if not getattr(app, "_mcp_bp_registered", False):
        app.register_blueprint(create_mcp_blueprint())
        app._mcp_bp_registered = True

    if not getattr(app, "_discovery_bp_registered", False):
        app.register_blueprint(create_discovery_blueprint())
        app._discovery_bp_registered = True

    if not getattr(app, "_timeline_bp_registered", False):
        app.register_blueprint(create_timeline_blueprint())
        app._timeline_bp_registered = True

    if not getattr(app, "_views_bp_registered", False):
        app.register_blueprint(create_views_blueprint())
        app.add_url_rule(
            "/",
            endpoint="index",
            view_func=app.view_functions["views.index"],
        )
        app._views_bp_registered = True

    if not getattr(app, "_auth_bp_registered", False):
        app.register_blueprint(create_auth_blueprint())
        # Provide legacy endpoint names for compatibility
        app.add_url_rule(
            "/login",
            endpoint="login",
            view_func=app.view_functions["authentication.login"],
        )
        app.add_url_rule(
            "/logout",
            endpoint="logout",
            view_func=app.view_functions["authentication.logout"],
        )
        app.add_url_rule(
            "/sso",
            endpoint="sso_login",
            view_func=app.view_functions["authentication.sso_login"],
        )
        app._auth_bp_registered = True

    from app.blueprints.ui import create_blueprint as create_ui_blueprint

    if not getattr(app, "_ui_bp_registered", False):
        app.register_blueprint(create_ui_blueprint())
        app._ui_bp_registered = True

    # get_active_groups()

    @app.after_request
    def add_security_headers(response):
        """Add common security headers to every response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Allow pages from this site to be embedded in iframes
        # without opening the application to clickjacking from
        # other domains.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def enforce_host_domain():
        """Block requests missing a domain when enforcement is enabled."""
        if config.ENFORCE_DOMAIN_IN_HOST:
            host = request.headers.get("Host", "")
            if "." not in host:
                abort(403)

    @app.context_processor
    def inject_footer_data():
        outdated = False
        try:
            from app.utils.github import is_update_available

            outdated = is_update_available(str(VERSION))
        except Exception as exc:
            logging.warning("Could not determine update status: %s", exc)

        return dict(
            VERSION=VERSION,
            VERSION_OUTDATED=outdated,
            COMMIT_HASH=COMMIT_HASH,
            NODE_ENV=NODE_ENV,
            CHYRON_SPEED=CHYRON_SPEED,
            NAV_ICON=NAV_ICON,
            HEALTH_STATUS_ALWAYS_VISIBLE=HEALTH_STATUS_ALWAYS_VISIBLE,
            CLOCK_OVERLAY=CLOCK_OVERLAY,
            CLOCK_DIGITAL=CLOCK_DIGITAL,
            CLOCK_NAVBAR=CLOCK_NAVBAR,
        )
