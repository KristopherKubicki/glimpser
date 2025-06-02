import csv
import glob
import hashlib
import inspect
from sqlalchemy import inspect as sa_inspect
import io
import json
import logging
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta

from functools import wraps
from threading import Lock, Thread
import queue

from flask import (
    abort,
    jsonify,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
    Response,
    make_response,
    stream_with_context,
)

from PIL import Image
from sqlalchemy import text
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import subprocess
import struct
import random

logging.getLogger("werkzeug").setLevel(logging.WARNING)

import app.config as config
from app.config import (
    API_KEY,
    SCREENSHOT_DIRECTORY,
    VIDEO_DIRECTORY,
    VERSION,
    BACKUP_PATH,
    backup_config,
    restore_config,
    SENSITIVE_SETTINGS,
)
from app.models import User, Summary
from app.utils import (
    scheduling,
    template_manager,
    video_archiver,
    screenshots,
    camera_discovery,
    prompt_optimizer,
    camera_fix,
)
from app.utils.screenshots import (
    is_chrome_debug_port_open,
    check_user_activity,
    capture_frame_from_stream,
)
from app.utils.db import SessionLocal, engine

try:
    COMMIT_HASH = (
        subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
        .decode()
        .strip()
    )
except Exception:
    COMMIT_HASH = "unknown"
NODE_ENV = os.getenv("NODE_ENV", "development")

# from app.models.log import Log
from app.utils.scheduling import log_cache, log_cache_lock
from app.utils.validators import validate_template_name, validate_update_data
from app.utils.profiling import profile_route, get_latency_stats
from scripts.update_chrome_shortcut import update_chrome_shortcuts


def restart_server():
    logging.info("Restarting server...")

    def delayed_restart():
        time.sleep(1)  # 1-second delay
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Start the delayed restart in a separate thread
    restart_thread = Thread(target=delayed_restart)
    restart_thread.start()


class TemplateName:
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


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
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
                session.pop("user_id", None)
                flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))

            expiry = session.get("expiry")
            if expiry and datetime.now() > datetime.strptime(
                expiry, "%Y-%m-%d %H:%M:%S"
            ):
                session.pop("user_id", None)
                flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))

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
                session.pop("user_id", None)
                flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))

            # Optional role checks could be added here
            return f(*args, **kwargs)

        # Handle missing or invalid authentication
        else:
            if api_key:
                return jsonify({"error": "Invalid API key"}), 401
            else:
                # When no session cookie is present the user might have cookies
                # disabled or the SESSION_COOKIE_SECURE flag could block the
                # cookie over HTTP. Provide a hint and log for easier debugging
                if "session" not in request.cookies:
                    flash("Login requires cookies. Check browser settings.", "error")
                    logging.debug("Missing session cookie from %s", request.remote_addr)
                return redirect(url_for("login", next=request.url))

    return decorated_function


# Function to read logs from the local text file and filter them based on query parameters
def read_logs_from_memory(
    level=None, source=None, start_date=None, end_date=None, search=None
):
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


def get_all_settings():
    session = SessionLocal()
    try:
        # Fetch all settings from the database
        db_settings = {
            row[0]: row[1]
            for row in session.execute(
                text("SELECT name, value FROM settings")
            ).fetchall()
        }

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
                lsettings_list.append({"name": sl["name"], "value": sl["value"]})

        return lsettings_list

    finally:
        session.close()


def update_setting(name: str, value: str) -> bool:

    name = name.replace("'", "")[:32]
    value = value.replace("'", "")[:1024]

    if not re.findall(r"^[A-Z_]+?$", name):
        return False

    session = SessionLocal()
    delta = False
    try:
        existing_setting = session.execute(
            text("SELECT value FROM settings WHERE name = :name"), {"name": name}
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
    finally:
        session.close()

    if delta is True:
        # Trigger server restart
        # is there a way to do this on a delay?
        restart_server()

    return True


def generate_video_stream(video_path: str):
    """Yield video data in chunks and restart when the end is reached."""

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
        logging.debug("Restarting video stream")


def generate_live_stream(url: str):
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
        while True:
            try:
                resp = session.get(url, timeout=5, stream=True)
                if resp.status_code == 200:
                    yield resp.content
                    failures = 0
                else:
                    logging.error(
                        "Failed to fetch image from %s (HTTP %s)", url, resp.status_code
                    )
                    failures += 1
            except GeneratorExit:
                break
            except Exception as e:
                logging.error("Error fetching image from %s: %s", url, e)
                failures += 1

            delay = min(base_delay * (2**failures), 30)
            time.sleep(delay)
        return

    command = [config.FFMPEG_PATH]
    if config.FFMPEG_HWACCEL and config.FFMPEG_HWACCEL.lower() != "false":
        command.extend(["-hwaccel", config.FFMPEG_HWACCEL])
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

    while True:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        try:
            while True:
                chunk = process.stdout.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
                if process.poll() is not None:
                    break
        except GeneratorExit:
            process.kill()
            process.wait(timeout=1)
            return
        finally:
            process.kill()
            process.wait(timeout=1)

        if process.returncode == 0:
            return

        logging.error("ffmpeg exited with %s, retrying", process.returncode)
        time.sleep(2)


login_attempts = {}
last_shot = None
last_time = None
active_groups = []
rtsp_sessions = {}


def get_active_groups():
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


def resize_and_pad(img, size, color=(0, 0, 0)):
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


lock = Lock()


def generate(
    group=None, camera=None, filename="latest_camera.png", rtsp=False, session_id=None
):
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
                                "Failed to open last shot %s: invalid image", last_shot
                            )
                            try:
                                os.remove(last_shot)
                            except OSError:
                                pass
                            last_shot = None
                    except Exception as e:
                        logging.error("Failed to open last shot %s: %s", last_shot, e)
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
                        if os.path.exists(os.path.join(path, filename)):
                            lfiles = [os.path.join(path, filename)]

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
                                except OSError:
                                    pass
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
                        except Exception:
                            pass

        if frame:
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


def generate_fast_mjpg(camera: str):
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


def allowed_filename(filename: str) -> bool:
    r"""Return ``True`` when ``filename`` contains only safe characters.

    The function first rejects any occurrence of ``".."`` to prevent
    directory traversal. It then matches the entire filename against the
    regular expression ``^[a-zA-Z0-9\.\-_]+?$`` which allows only letters,
    numbers, periods, hyphens, and underscores. A match means the filename
    is free of path separators or other dangerous characters.
    """

    if ".." in filename:
        return False

    if re.findall(r"^[a-zA-Z0-9\.\-_]+?$", filename):

        return True

    return False


def init_routes(app):
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

    @app.context_processor
    def inject_footer_data():
        outdated = False
        try:
            from app.utils.github import is_update_available

            outdated = is_update_available(str(VERSION))
        except Exception:
            pass

        return dict(
            VERSION=VERSION,
            VERSION_OUTDATED=outdated,
            COMMIT_HASH=COMMIT_HASH,
            NODE_ENV=NODE_ENV,
        )

    # Add a new route for the extended health check
    @app.route("/health")
    @login_required
    @profile_route("/health")
    def health_check():

        scheduler_status = "failed"
        free_gb = 0

        metrics = scheduling.get_system_metrics()

        # Define thresholds for nominal performance
        cpu_threshold = 80  # 80% CPU usage
        memory_threshold = 80  # 80% memory usage
        thread_threshold = 100  # 100 threads # should be tied to the thread count in the config, right?
        open_file_threshold = 1024  # thats a lot
        disk_threshold = 95  # almost full

        # Check if metrics are nominal and collect error messages
        error_messages = []
        is_nominal = True

        if metrics["cpu_usage"] >= cpu_threshold:
            is_nominal = False
            error_messages.append(f"CPU usage is high: {metrics['cpu_usage']}%")
        if metrics["memory_usage"] >= memory_threshold:
            is_nominal = False
            error_messages.append(f"Memory usage is high: {metrics['memory_usage']}%")
        if metrics["thread_count"] >= thread_threshold:
            is_nominal = False
            error_messages.append(f"Thread count is high: {metrics['thread_count']}")
        if metrics["open_files"] >= open_file_threshold:
            is_nominal = False
            error_messages.append(f"Too many open files: {metrics['open_files']}")
        if metrics["disk_usage"] >= disk_threshold:
            is_nominal = False
            error_messages.append(f"Disk usage is high: {metrics['disk_usage']}%")

        try:
            # 0h 1m 6s
            if (
                len(metrics["uptime"]) < 9 and "0h 0m " in metrics["uptime"]
            ):  # first ten seconds...
                is_nominal = False
                error_messages.append("System just started, still initializing")
        except Exception:
            is_nominal = False
            error_messages.append("Error getting system uptime")

        ######
        #  consider rolling these into the metrics
        try:
            # Check database connection
            session = SessionLocal()
            session.execute(text("SELECT 1"))
            session.close()
            db_status = "connected"
        except Exception:
            is_nominal = False
            db_status = "disconnected"
            error_messages.append("Database connection failed")

        try:
            # Check if scheduler is running
            scheduler_status = "running" if scheduling.scheduler.running else "stopped"
            if scheduler_status != "running":
                is_nominal = False
                error_messages.append("Scheduler is not running")
        except Exception:
            is_nominal = False
            scheduler_status = "failed"
            error_messages.append("Error checking scheduler status")

        #
        ######

        return (
            jsonify(
                {
                    "status": "healthy" if is_nominal else "degraded",
                    "metrics": metrics,
                    "nominal": is_nominal,
                    "database": db_status,
                    "scheduler": scheduler_status,
                    "free_disk_space_gb": free_gb,
                    "error_messages": error_messages,
                }
            ),
            200,
        )  # always return 200, but might be degraded.

    @app.route("/danger_status")
    @login_required
    @profile_route("/danger_status")
    def danger_status():
        """Return whether Danger mode can be used."""
        port_open = is_chrome_debug_port_open("127.0.0.1", 9222)
        idle = not check_user_activity(timeout=1)
        enabled = config.get_setting("DANGER_MODE", "True") == "True"
        return jsonify(
            {
                "port_open": port_open,
                "idle": idle,
                "enabled": enabled,
                "ready": port_open and idle and enabled,
            }
        )

    @app.route("/danger", methods=["GET", "POST"])
    @login_required
    def danger_mode():
        if request.method == "POST":
            enabled = "enabled" in request.form
            update_setting("DANGER_MODE", "True" if enabled else "False")
            return redirect(url_for("danger_mode"))

        current = config.get_setting("DANGER_MODE", "True") == "True"
        return render_template("danger.html", enabled=current)

    @app.route("/api/discover")
    @profile_route("/api/discover")
    def api_discover():
        api_info = {
            "version": "1.0",
            "endpoints": [
                {
                    "path": "/health",
                    "method": "GET",
                    "description": "Check the health status of the API",
                    "authentication_required": False,
                },
                {
                    "path": "/danger_status",
                    "method": "GET",
                    "description": "Check if Danger mode is ready",
                    "authentication_required": False,
                },
                {
                    "path": "/api/discover",
                    "method": "GET",
                    "description": "Get information about available API endpoints",
                    "authentication_required": False,
                },
                {
                    "path": "/login",
                    "method": "GET, POST",
                    "description": "User login endpoint",
                    "authentication_required": False,
                },
                {
                    "path": "/logout",
                    "method": "GET",
                    "description": "User logout endpoint",
                    "authentication_required": True,
                },
                {
                    "path": "/",
                    "method": "GET",
                    "description": "Main index page",
                    "authentication_required": True,
                },
                {
                    "path": "/templates",
                    "method": "GET, POST, DELETE",
                    "description": "Manage templates",
                    "authentication_required": True,
                },
                {
                    "path": "/settings",
                    "method": "GET, POST",
                    "description": "Manage application settings",
                    "authentication_required": True,
                },
            ],
        }
        return jsonify(api_info), 200

    @app.route("/mcp/tools")
    @login_required
    def mcp_tools():
        """Return the list of tools exposed by the configured MCP server."""
        from app.utils import mcp

        tools = mcp.list_tools_sync()
        return jsonify(tools)

    @app.route("/mcp/tool/<string:name>", methods=["POST"])
    @login_required
    def mcp_call_tool(name):
        """Call a tool on the configured MCP server."""
        from app.utils import mcp

        params = request.get_json(silent=True) or {}
        result = mcp.call_tool_sync(name, params)
        return jsonify(result)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        ip_address = request.remote_addr
        now = datetime.now()

        # Check if the IP address is locked out
        if (
            ip_address in login_attempts
            and login_attempts[ip_address]["locked_until"] > now
        ):
            flash("Too many failed attempts. Please try again later.", "error")
            logging.warning("Locked login attempt from %s", ip_address)
            return render_template("login.html"), 429

        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]

            db_session = SessionLocal()
            try:
                user = db_session.query(User).filter_by(username=username).first()
            finally:
                db_session.close()

            if user and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                session["expiry"] = (
                    now + timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)
                ).strftime("%Y-%m-%d %H:%M:%S")
                session.permanent = True
                login_attempts.pop(
                    ip_address, None
                )  # Reset attempts on successful login
                logging.info("Successful login for %s from %s", username, ip_address)
                return redirect(url_for("index"))
            else:
                # Record the failed attempt
                if ip_address not in login_attempts:
                    login_attempts[ip_address] = {"attempts": 1, "locked_until": now}
                else:
                    login_attempts[ip_address]["attempts"] += 1

                # Lockout after 5 failed attempts
                if login_attempts[ip_address]["attempts"] >= 5:
                    login_attempts[ip_address]["locked_until"] = now + timedelta(
                        hours=24
                    )

                # Rate limit after 2 attempts per minute
                if login_attempts[ip_address]["attempts"] % 2 == 0:
                    login_attempts[ip_address]["locked_until"] = now + timedelta(
                        minutes=1
                    )
                logging.warning(
                    "Failed login attempt for %s from %s", username, ip_address
                )
                flash("Invalid username or password", "error")
        return render_template("login.html")

    @app.route("/sso", methods=["GET"])
    def sso_login():
        token = request.args.get("token") or request.headers.get("X-SSO-Token")
        if token != config.SSO_TOKEN or not token:
            flash("Invalid SSO token", "error")
            logging.warning("Invalid SSO token from %s", request.remote_addr)
            return redirect(url_for("login"))

        db_session = SessionLocal()
        try:
            user = (
                db_session.query(User).filter_by(username=config.SSO_USERNAME).first()
            )
        finally:
            db_session.close()

        if not user:
            flash("Configured SSO user not found", "error")
            logging.error("SSO user %s not found", config.SSO_USERNAME)
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["expiry"] = (
            datetime.now() + timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)
        ).strftime("%Y-%m-%d %H:%M:%S")
        session.permanent = True
        flash("Logged in via SSO", "success")
        logging.info("SSO login for %s from %s", user.username, request.remote_addr)
        return redirect(url_for("index"))

    @app.route("/help")
    @login_required
    def help_page():
        return render_template("help.html")

    @app.route("/settings_help")
    @login_required
    def settings_help():
        """Display detailed explanations for each configuration option."""
        return render_template("settings_explanation.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.pop("user_id", None)
        flash("You have been logged out successfully.", "success")
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        """Render the index page with available templates."""
        template_details = template_manager.get_templates()
        return render_template("index.html", template_details=template_details)

    def get_active_templates():
        templates = template_manager.get_templates()
        active_cameras = []
        for id, template in templates.items():
            template.get("name")
            last_screenshot_time = template.get("last_screenshot_time")
            if last_screenshot_time:
                last_update = datetime.strptime(
                    last_screenshot_time, "%Y-%m-%d %H:%M:%S"
                )
                if last_update > datetime.utcnow() - timedelta(days=1):
                    active_cameras.append(template)
        return active_cameras

    @app.route("/submit_image/<string:template_name>", methods=["POST"])
    @login_required
    def submit_image(template_name: TemplateName):
        """
        Endpoint to receive and process an image submitted by a remote service or camera.
        """
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        # Check if the template exists and get the canonical name stored
        # in the database. ``get_template`` returns an attribute dictionary
        # or ``{}`` when the name is not present.
        details = template_manager.get_template(template_name)
        if not details:
            return jsonify({"status": "error", "message": "Template not found"}), 404
        # Prefer the name from the database (it may contain canonical casing)
        template_name = details.get("name", template_name)

        # Check if the request has the file part
        if "file" not in request.files:
            return (
                jsonify({"status": "error", "message": "No file part in the request"}),
                400,
            )

        file = request.files["file"]

        # If the user does not select a file, the browser submits an empty file without a filename
        if file.filename == "":
            return jsonify({"status": "error", "message": "No selected file"}), 400

        if file and allowed_filename(file.filename):
            # Generate a unique timestamped filename
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            filename = f"{template_name}_{timestamp}.png.tmp"
            output_path = os.path.join(SCREENSHOT_DIRECTORY, template_name, filename)
            # if not os.path.normpath(output_path).startswith(SCREENSHOT_DIRECTORY):
            #    abort(400)

            # Save the file to a temporary location
            file.save(output_path)

            # Add a timestamp to the image and remove the ".tmp" extension
            screenshots.add_timestamp(output_path, name=template_name)
            final_path = output_path.rstrip(".tmp")
            os.rename(output_path, final_path)

            # Update the template's last screenshot time
            template_manager.update_last_screenshot_time(template_name)

            return (
                jsonify(
                    {"status": "success", "message": "Image submitted successfully"}
                ),
                200,
            )
        else:
            return jsonify({"status": "error", "message": "Invalid file format"}), 400

    @app.route("/stream.png")
    @login_required
    def stream_png():

        latest_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            SCREENSHOT_DIRECTORY,
            "latest_camera.png",
        )
        if os.path.exists(latest_path):
            if screenshots._is_valid_png(latest_path):
                return send_file(latest_path)
            logging.warning("Invalid latest camera image removed: %s", latest_path)
            try:
                os.remove(latest_path)
            except OSError:
                pass

        global last_time, last_shot
        # implement some simple caching so the server doesn't get crushed
        if (
            last_time
            and time.time() - last_time < 1
            and last_shot
            and os.path.exists(last_shot)
        ):
            return send_file(last_shot)

        templates = template_manager.get_templates()
        sorted_templates = sorted(
            templates.items(),
            key=lambda x: (x[1].get("last_video_time", 0) or 0),
            reverse=True,
        )

        most_recent_time = 0
        most_recent_file = None
        last_file = None
        for _, template in sorted_templates:
            name = validate_template_name(template.get("name"))
            if name is None:
                continue
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                SCREENSHOT_DIRECTORY,
                name,
            )
            lfiles = [f for f in glob.glob(path + "/*.png") if os.path.isfile(f)]
            if not lfiles:
                continue
            lfiles.sort(key=os.path.getmtime)
            last_file = lfiles[-1]
            if (
                os.path.exists(last_file)
                and os.path.getmtime(last_file) > most_recent_time
            ):
                most_recent_file = last_file
                most_recent_time = os.path.getmtime(last_file)
        if most_recent_file is None:
            abort(404)

        last_time = time.time()
        last_shot = most_recent_file

        if os.path.exists(most_recent_file):
            return send_file(most_recent_file)
        if last_file and os.path.exists(last_file):
            return send_file(last_file)  # better than nothing
        abort(404)

    @app.route(
        "/test.rtsp",
        methods=[
            "OPTIONS",
            "DESCRIBE",
            "SETUP",
            "PLAY",
            "PAUSE",
            "GET_PARAMETER",
            "TEARDOWN",
        ],
    )
    def handle_rtsp():

        session_id = request.headers.get("Session", str(uuid.uuid4()))
        cseq = request.headers.get("CSeq", "0")

        if request.method == "OPTIONS":
            return Response(
                "Public: OPTIONS, DESCRIBE, SETUP, PLAY, PAUSE, GET_PARAMETER, TEARDOWN",
                headers={"CSeq": cseq},
            )

        elif request.method == "DESCRIBE":
            sdp = (
                "v=0\r\n"
                "o=- 0 0 IN IP4 127.0.0.1\r\n"
                "s=Glimpser RTSP Stream\r\n"
                "t=0 0\r\n"
                "m=video 0 RTP/AVP 26\r\n"
                "a=rtpmap:26 JPEG/90000\r\n"
                "a=control:streamid=0\r\n"
            )
            return Response(
                sdp,
                mimetype="application/sdp",
                headers={"CSeq": cseq, "Content-Base": request.url},
            )

        elif request.method == "SETUP":
            if session_id not in rtsp_sessions:
                rtsp_sessions[session_id] = {
                    "state": "READY",
                    "seq": random.randint(0, 65535),
                    "timestamp": random.randint(0, 0xFFFFFFFF),
                    "ssrc": random.randint(0, 0xFFFFFFFF),
                    "last_keepalive": time.time(),
                }

            transport = request.headers.get("Transport", "")
            client_ports = (0, 0)
            match = re.search(r"client_port=(\d+)(?:-(\d+))?", transport)
            if match:
                first = int(match.group(1))
                second = int(match.group(2) or first + 1)
                client_ports = (first, second)

            server_ports = (5004, 5005)
            session = rtsp_sessions[session_id]
            session["client_ports"] = client_ports
            session["server_ports"] = server_ports

            transport_response = transport
            if transport_response and not transport_response.endswith(";"):
                transport_response += ";"
            transport_response += f"server_port={server_ports[0]}-{server_ports[1]};ssrc={session['ssrc']}"

            return Response(
                headers={
                    "CSeq": cseq,
                    "Session": session_id,
                    "Transport": transport_response,
                }
            )

        elif request.method == "PLAY":
            if session_id not in rtsp_sessions:
                abort(454)  # Session Not Found
            rtsp_sessions[session_id]["state"] = "PLAYING"
            return Response(
                headers={
                    "CSeq": cseq,
                    "Session": session_id,
                    "RTP-Info": "url=rtsp://example.com/test.rtsp/streamid=0;seq=0;rtptime=0",
                }
            )

        elif request.method == "PAUSE":
            if session_id not in rtsp_sessions:
                abort(454)
            rtsp_sessions[session_id]["state"] = "PAUSED"
            return Response(headers={"CSeq": cseq, "Session": session_id})

        elif request.method == "GET_PARAMETER":
            if session_id not in rtsp_sessions:
                abort(454)
            rtsp_sessions[session_id]["last_keepalive"] = time.time()
            return Response(headers={"CSeq": cseq, "Session": session_id})

        elif request.method == "TEARDOWN":
            if session_id in rtsp_sessions:
                del rtsp_sessions[session_id]
            return Response(
                headers={
                    "CSeq": cseq,
                    "Session": session_id,
                }
            )

        return "Method Not Allowed", 405

    @app.route("/stream.mjpg", methods=["GET"])
    def stream_mjpg():
        group = request.args.get("group")
        camera = request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        return Response(
            generate(group=group, camera=camera, filename="latest_camera.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/motion.mjpg", methods=["GET"])
    def motion_mjpg():
        group = request.args.get("group")
        camera = request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        return Response(
            generate(group=group, camera=camera, filename="last_motion.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/caption.mjpg", methods=["GET"])
    def caption_mjpg():
        group = request.args.get("group")
        camera = request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        logging.debug("last caption")
        return Response(
            generate(group=group, camera=camera, filename="last_caption.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/motion_caption.mjpg", methods=["GET"])
    def motion_caption_mjpg():
        group = request.args.get("group")
        camera = request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        logging.debug("last motion caption")
        return Response(
            generate(group=group, camera=camera, filename="last_motion_caption.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/fast_stream.mjpg", methods=["GET"])
    @login_required
    def fast_stream_mjpg():
        camera = request.args.get("camera")
        if not camera:
            abort(400, "camera parameter required")
        if not template_manager.get_template(camera):
            abort(404)
        return Response(
            generate_fast_mjpg(camera),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/rtsp_stream")
    def rtsp_stream():
        session_id = request.args.get("session")
        if (
            session_id not in rtsp_sessions
            or rtsp_sessions[session_id]["state"] != "PLAYING"
        ):
            abort(400, "Invalid session or session not in PLAYING state")
        return Response(
            generate(rtsp=True, session_id=session_id), mimetype="application/x-rtp"
        )

    @app.route("/stream.mp4")
    @login_required
    def stream_mp4():
        # Default group
        lgroup = "all"

        # Get the group from the request arguments and validate
        group = request.args.get("group")
        if group and re.match(r"^[a-zA-Z0-9_]+$", group):
            lgroup = group
        else:
            # If the group is provided but invalid, return a 400 Bad Request
            if group:
                abort(400, "Invalid group name. Group name must be alphanumeric.")

        lgroup = secure_filename(lgroup)
        video_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            VIDEO_DIRECTORY,
            f"{lgroup}_in_process.mp4",
        )

        if not os.path.exists(video_path):
            abort(404)

        # Stream the video in small chunks for continuous playback
        return Response(
            stream_with_context(generate_video_stream(video_path)),
            mimetype="video/mp4",
        )

    @app.route("/live_video")
    @login_required
    def live_video():
        camera = request.args.get("camera")
        if not camera:
            abort(400, "camera parameter required")
        details = template_manager.get_template(camera)
        if not details:
            abort(404)
        url = details.get("url")
        if not url:
            abort(404)
        return Response(
            stream_with_context(generate_live_stream(url)),
            mimetype="video/mp4",
        )

    @app.route("/stream.m3u8")
    @login_required
    def playlist_m3u8():
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", VIDEO_DIRECTORY
        )

        # Check if the video directory exists
        if not os.path.exists(path):
            abort(404)

        camera = request.args.get("camera")
        group = request.args.get("group")

        # Generate playlist content
        playlist_content = "#EXTM3U\n"
        playlist_content += "#EXT-X-VERSION:3\n"
        playlist_content += (
            "#EXT-X-TARGETDURATION:10\n"  # Assuming each segment is up to 10 seconds
        )
        playlist_content += "#EXT-X-MEDIA-SEQUENCE:0\n"

        templates = template_manager.get_templates()

        filtered_templates = []
        if camera:
            camera = validate_template_name(camera)
            if camera is None:
                abort(400, "Invalid camera name")
            details = templates.get(camera)
            if details:
                filtered_templates.append((camera, details))
        elif group:
            if not re.match(r"^[a-zA-Z0-9_]+$", group):
                abort(400, "Invalid group name. Group name must be alphanumeric.")
            for name, details in templates.items():
                groups = [g.strip() for g in details.get("groups", "").split(",")]
                if group in groups:
                    valid = validate_template_name(name)
                    if valid:
                        filtered_templates.append((valid, details))
        else:
            for name, details in templates.items():
                valid = validate_template_name(name)
                if valid:
                    filtered_templates.append((valid, details))

        # Sort templates by 'last_video_time' descending
        sorted_templates = sorted(
            filtered_templates,
            key=lambda x: (x[1].get("last_video_time", 0) or 0),
            reverse=True,
        )

        for camera_name, _ in sorted_templates:
            lkey = generate_timed_hash()
            video_path = f"{request.url_root}last_video/{camera_name}?timed_key={lkey}"
            playlist_content += f"#EXTINF:10.0,{camera_name}\n{video_path}\n"

        playlist_content += "#EXT-X-ENDLIST\n"

        return Response(playlist_content, mimetype="application/x-mpegURL")

    @app.route("/stream")
    @login_required
    def stream():
        # Get a list of active cameras (with updates within the last 1 day)
        return render_template("stream.html")

    @app.route("/groups")
    @login_required
    def get_groups():
        # Assuming you have a function that returns a list of unique groups
        groups = get_active_groups()
        return jsonify(groups)

    @app.route("/captions")
    @login_required
    def captions():

        # Load the most recent summaries from the database
        entries = []
        try:
            session_db = SessionLocal()
            try:
                records = (
                    session_db.query(Summary)
                    .order_by(Summary.timestamp.desc())
                    .limit(5)
                    .all()
                )
                for rec in records:
                    try:
                        entries.append(json.loads(rec.content))
                    except Exception:
                        pass
            finally:
                session_db.close()
        except Exception:
            entries = []

        # Get templates and calculate next capture time
        templates = template_manager.get_templates()
        for name, template in templates.items():
            last_screenshot_time = template.get("last_screenshot_time")
            frequency = int(
                template.get("frequency", 30)
            )  # Default to 30 minutes if not set

            if last_screenshot_time:
                last_screenshot = datetime.strptime(
                    last_screenshot_time, "%Y-%m-%d %H:%M:%S"
                )
                next_screenshot = last_screenshot + timedelta(minutes=frequency)
                template["next_screenshot_time"] = next_screenshot.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                template["next_screenshot_time"] = None

            templates[name]["screenshot_count"] = template_manager.get_screenshot_count(
                name
            )
            templates[name]["video_count"] = template_manager.get_video_count(name)
            templates[name]["storage_usage"] = template_manager.get_storage_usage(name)
            templates[name]["llm_response_count"] = (
                template_manager.get_llm_response_count(name)
            )
            templates[name]["llm_cost_estimate"] = (
                template_manager.get_llm_cost_estimate(name)
            )

        # Get a list of active cameras (with updates within the last 1 day)
        return render_template(
            "captions.html",
            template_details=templates,
            lcaptions=entries,
        )

    @app.route("/download_captions_tsv")
    @login_required
    def download_captions_tsv():
        """Download all template captions as a TSV file."""
        templates = template_manager.get_templates()

        # Create a StringIO object to write the TSV data
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t")

        # Write header row
        writer.writerow(["name", "groups", "notes", "last_caption"])

        # Write data rows
        for name, template in templates.items():
            writer.writerow(
                [
                    name,
                    template.get("groups", ""),
                    template.get("notes", ""),
                    template.get("last_caption", ""),
                ]
            )

        # Create response with TSV file
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/tab-separated-values",
            headers={"Content-Disposition": "attachment;filename=captions.tsv"},
        )

    @app.route("/upload_captions_tsv", methods=["POST"])
    @login_required
    def upload_captions_tsv():
        """Upload and process a TSV file to update template captions."""
        if "tsv_file" not in request.files:
            flash("No file part", "error")
            return redirect(url_for("captions"))

        file = request.files["tsv_file"]

        if file.filename == "":
            flash("No selected file", "error")
            return redirect(url_for("captions"))

        if file and file.filename.endswith(".tsv"):
            # Read the TSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.reader(stream, delimiter="\t")

            # Skip header row
            next(reader, None)

            # Process each row
            updated_count = 0
            for row in reader:
                if len(row) >= 4:
                    name, groups, notes, last_caption = row[:4]

                    # Validate template name
                    template_name = validate_template_name(name)
                    if template_name is None:
                        continue

                    # Get existing template
                    template = template_manager.get_template(template_name)
                    if template:
                        # Update template fields
                        updates = {"groups": groups, "notes": notes}

                        # Only update last_caption if it's different
                        if last_caption and last_caption != template.get(
                            "last_caption", ""
                        ):
                            updates["last_caption"] = last_caption
                            updates["last_caption_time"] = datetime.utcnow().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )

                        # Save the updated template
                        if template_manager.save_template(template_name, updates):
                            updated_count += 1

            flash(f"Successfully updated {updated_count} templates", "success")
            return redirect(url_for("captions"))

        flash("Invalid file format. Please upload a TSV file.", "error")
        return redirect(url_for("captions"))

    @app.route("/live")
    @login_required
    def live():
        """Render the live view page.

        Optionally filter to a single camera when ``camera`` is provided in the
        query string. This avoids loading metadata for all cameras when embedding
        the live view for a specific template.
        """

        camera = request.args.get("camera")
        if camera:
            camera = validate_template_name(camera)
            if camera is None:
                abort(400, "Invalid camera name")
            details = template_manager.get_template(camera)
            if not details:
                abort(404)
            templates = {camera: details}
        else:
            templates = template_manager.get_templates()

        return render_template("live.html", template_details=templates)

    @app.route("/latest_frame/<string:template_name>")
    @login_required
    def latest_frame(template_name: TemplateName):
        """
        Serve the latest frame for a specific camera.
        """
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            SCREENSHOT_DIRECTORY,
            template_name,
        )
        if not os.path.exists(path):
            abort(404)

        latest_file = max(
            (f for f in os.listdir(path) if f.endswith(".png")),
            key=lambda f: os.path.getmtime(os.path.join(path, f)),
        )

        if latest_file:
            return send_file(os.path.join(path, latest_file), mimetype="image/png")

        abort(404)

    @app.route("/last_teaser")
    @login_required
    def serve_teaser():
        """Serve the teaser video for a specific group."""

        group = request.args.get("group")
        if group and not re.match(r"^[a-zA-Z0-9_]+$", group):
            abort(400, "Invalid group name. Group name must be alphanumeric.")

        lgroup = secure_filename(group) if group else "all"
        base_path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", VIDEO_DIRECTORY
        )
        if not os.path.exists(base_path):
            abort(404)

        video_path = os.path.join(base_path, f"{lgroup}_in_process.mp4")
        if os.path.exists(video_path):
            return send_file(video_path)

        abort(404)

    @app.route("/last_video/<string:template_name>")
    @login_required
    def serve_video(template_name: TemplateName):
        """
        Serve a specific video by template name.
        """
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        # Placeholder logic to serve the video
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            VIDEO_DIRECTORY,
            template_name,
        )
        if not os.path.exists(path):
            abort(404)

        if os.path.exists(path + "/in_process.mp4"):
            return send_file(path + "/in_process.mp4")

        abort(404)

    @app.route("/last_screenshot/<string:template_name>")
    @login_required
    def serve_screenshot(template_name: TemplateName):
        """
        Serve a specific screenshot by template name.
        """

        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        for group_camera in re.findall(r"^group-(.+?)$", template_name):
            path = os.path.join(
                os.path.dirname(os.path.join(__file__)),
                "..",
                SCREENSHOT_DIRECTORY,
                "%s_latest_camera.png" % group_camera,
            )
            if os.path.exists(path):
                return send_file(path)
            abort(404)

        # Placeholder logic to serve the screenshot
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            SCREENSHOT_DIRECTORY,
            template_name,
        )
        if not os.path.exists(path):
            abort(404)

        lfiles = [f for f in glob.glob(path + "/*.png") if os.path.isfile(f)]
        lfiles.sort(key=os.path.getmtime, reverse=True)
        for shot in lfiles:
            try:
                if os.path.getsize(shot) > 0 and screenshots._is_valid_png(shot):
                    return send_file(shot)
            except OSError:
                continue

        abort(404)

    @app.route("/compile_teaser", methods=["POST"])
    @login_required
    def take_compile():
        video_archiver.compile_to_teaser()
        return jsonify({"status": "success", "message": "Compilation taken"})

    @app.route("/upload_screenshot/<string:template_name>", methods=["POST"])
    @login_required
    def upload_screenshot(template_name: TemplateName):
        """
        Endpoint to upload a screenshot manually.
        """

        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        if "image_file" not in request.files:
            return (
                jsonify({"status": "error", "message": "No image file provided"}),
                400,
            )

        image_file = request.files["image_file"]
        if image_file.filename == "":
            return (
                jsonify({"status": "error", "message": "No image file provided"}),
                400,
            )

        logging.debug("Uploading screenshot for %s", template_name)
        templates = template_manager.get_templates()
        if templates.get(template_name) is None:
            abort(404)

        if not allowed_filename(
            image_file.filename
        ) or not image_file.filename.lower().endswith(".png"):
            return (
                jsonify({"status": "error", "message": "Invalid file name"}),
                400,
            )

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            image_file.save(temp_file.name)
            if not screenshots._is_valid_png(temp_file.name):
                os.unlink(temp_file.name)
                return (
                    jsonify({"status": "error", "message": "Invalid image file"}),
                    400,
                )

            scheduling.update_camera(
                template_name, templates.get(template_name), image_file=temp_file.name
            )

        # Clean up the temporary file
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

        return jsonify(
            {"status": "success", "message": f"Screenshot for {template_name} uploaded"}
        )

    @app.route("/take_screenshot/<string:template_name>", methods=["POST", "GET"])
    @login_required
    def take_screenshot(template_name: TemplateName):
        """
        Endpoint to trigger screenshot capture manually.
        """
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        templates = template_manager.get_templates()
        # handle if this doesn't exist
        if templates.get(template_name) is None:
            abort(404)

        motion_flag = request.args.get("motion", "false").lower() in [
            "1",
            "true",
            "yes",
        ]
        scheduling.update_camera(
            template_name, templates.get(template_name), motion=motion_flag
        )
        return jsonify(
            {"status": "success", "message": f"Screenshot for {template_name} taken"}
        )

    @app.route("/update_video/<string:template_name>", methods=["POST"])
    @login_required
    def update_video(template_name: TemplateName):
        """Endpoint to trigger screenshot capture manually."""
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        templates = template_manager.get_templates()
        # handle if this doesn't exist
        if templates.get(template_name) is None:
            abort(404)
        camera_path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            SCREENSHOT_DIRECTORY,
            template_name,
        )

        video_path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            VIDEO_DIRECTORY,
            template_name,
        )

        if os.path.exists(camera_path) and os.path.exists(video_path):
            video_archiver.compile_to_video(camera_path, video_path)
            return jsonify(
                {
                    "status": "success",
                    "message": f"Screenshot for {template_name} taken",
                }
            )

    @app.route("/templates", methods=["GET", "POST", "DELETE"])
    @login_required
    def manage_templates():
        if request.method == "POST":
            data = request.json
            template_name = validate_template_name(data["name"])
            if template_name is None:
                abort(404)
            if template_manager.save_template(template_name, data):
                return jsonify({"status": "success", "message": "Template saved"})

        elif request.method == "GET":
            group = request.args.get("group")
            search_query = request.args.get("search", "").lower()
            templates = template_manager.get_templates()

            filtered_templates = {}
            for name, template in templates.items():
                template_groups = template.get("groups", "").split(",")
                if (group == "all" or group in template_groups) and (
                    not search_query
                    or search_query in name.lower()
                    or search_query in template.get("url", "").lower()
                    or any(search_query in g.lower() for g in template_groups)
                ):
                    filtered_templates[name] = template

            return jsonify(filtered_templates)

        elif request.method == "DELETE":
            data = request.json
            template_name = validate_template_name(data["name"])
            if template_name is None:
                abort(404)
            if template_manager.delete_template(template_name):
                return jsonify({"status": "success", "message": "Template deleted"})
            else:
                return (
                    jsonify({"status": "failure", "message": "Template not found"}),
                    404,
                )

    @app.route("/templates/<string:template_name>")
    @login_required
    def template_details(template_name: TemplateName):
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        templates = template_manager.get_templates()
        template_details = templates.get(template_name)
        if template_details is None:
            abort(404)  # Template not found
        lscreenshots = template_manager.get_screenshots_for_template(template_name)
        lvideos = template_manager.get_videos_for_template(template_name)
        return render_template(
            "template_details.html",
            template_name=template_name,
            template_details=template_details,
            screenshots=lscreenshots,
            videos=lvideos,
        )

    @app.route("/screenshots/<string:name>")
    @login_required
    def list_screenshots(name: TemplateName):
        """Return a JSON list of screenshot files for ``name``."""

        template_name = validate_template_name(name)
        if template_name is None:
            abort(404)

        lscreens = template_manager.get_screenshots_for_template(template_name)
        return jsonify({"screenshots": lscreens})

    @app.route("/generate_prompt/<string:template_name>", methods=["POST"])
    @login_required
    def generate_prompt_route(template_name: TemplateName):
        """Return a suggested caption prompt for ``template_name``."""

        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        prompt = prompt_optimizer.generate_prompt(template_name)
        return jsonify({"prompt": prompt})

    @app.route("/suggest_fix/<string:template_name>", methods=["POST"])
    @login_required
    def suggest_fix_route(template_name: TemplateName):
        """Return diagnostic info and replacement URL suggestions."""

        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        details = template_manager.get_template(template_name)
        if not details:
            abort(404)

        url = details.get("url", "")
        xpaths = [details.get("popup_xpath", ""), details.get("dedicated_xpath", "")]
        info = camera_fix.check_camera_template(url, xpaths)
        return jsonify(info)

    @app.route("/screenshots/<string:name>/<string:filename>")
    @login_required
    def uploaded_file(name: TemplateName, filename: str):
        template_name = validate_template_name(name)
        if template_name is None or not allowed_filename(filename):
            abort(404)

        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            SCREENSHOT_DIRECTORY,
            template_name,
        )

        if not os.path.exists(path):
            abort(404)

        return send_from_directory(path, filename)

    def delete_setting(name: str) -> bool:
        name = name.replace("'", "")[:32]
        if not re.findall(r"^[A-Z_]+?$", name):
            return False

        session = SessionLocal()
        try:
            session.execute(
                text("DELETE FROM settings WHERE name = :name"), {"name": name}
            )
            session.commit()
        finally:
            session.close()

        return True

    @app.route("/videos/<string:name>")
    @login_required
    def list_videos(name: TemplateName):
        """Return a JSON list of video files for ``name``."""

        template_name = validate_template_name(name)
        if template_name is None:
            abort(404)

        lvideos = template_manager.get_videos_for_template(template_name)
        return jsonify({"videos": lvideos})

    @app.route("/videos/<string:name>/<string:filename>")
    @login_required
    def view_video(name: TemplateName, filename: str):
        template_name = validate_template_name(name)
        if template_name is None or not allowed_filename(filename):
            abort(404)

        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            VIDEO_DIRECTORY,
            template_name,
        )

        if not os.path.exists(path):
            abort(404)

        return send_from_directory(path, filename)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            email_settings = [
                "EMAIL_ENABLED",
                "EMAIL_SENDER",
                "EMAIL_RECIPIENTS",
                "EMAIL_SMTP_SERVER",
                "EMAIL_SMTP_PORT",
                "EMAIL_USE_TLS",
                "EMAIL_USERNAME",
                "EMAIL_PASSWORD",
            ]
            action = request.form.get("action")
            if action == "add":
                new_name = request.form.get("new_name")
                new_value = request.form.get("new_value")
                if new_name and new_value:
                    update_setting(new_name, new_value)
            elif action == "delete":
                name_to_delete = request.form.get("name_to_delete")
                if name_to_delete:
                    delete_setting(name_to_delete)
            elif action == "update_email":
                for setting in email_settings:
                    value = request.form.get(setting)
                    if value is not None:
                        update_setting(setting, value)
            elif action == "backup":
                if backup_config():
                    flash("Configuration backed up successfully", "success")
                else:
                    flash("Failed to backup configuration", "error")
            elif action == "download":
                if os.path.exists(BACKUP_PATH):
                    return send_file(
                        BACKUP_PATH,
                        as_attachment=True,
                        download_name="config_backup.json",
                    )
                else:
                    flash("No backup file found", "error")
            elif action == "upload":
                if "file" not in request.files:
                    flash("No file part", "error")
                else:
                    file = request.files["file"]
                    if file.filename == "":
                        flash("No selected file", "error")
                    elif file and allowed_file(file.filename):
                        file.save(BACKUP_PATH)
                        restore_config()
                        flash("Configuration restored successfully", "success")
                    else:
                        flash("Invalid file type", "error")
            elif action == "update_shortcut":
                if update_chrome_shortcuts():
                    flash("Chrome shortcuts updated", "success")
                else:
                    flash("Failed to update shortcuts", "error")
            else:
                for name, value in request.form.items():
                    if (
                        name
                        not in ["action", "new_name", "new_value", "name_to_delete"]
                        + email_settings
                    ):
                        update_setting(name, value)
            return redirect(url_for("settings"))

        settings = get_all_settings()
        return render_template("settings.html", settings=settings)

    # Retained for backwards compatibility; redirect to the health endpoint.
    @app.route("/system_metrics")
    def system_metrics():
        return redirect(url_for("health_check"))

    def allowed_file(filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() == "json"

    @app.route("/update_template/<string:template_name>", methods=["POST"])
    @login_required
    def update_template(template_name: TemplateName):
        template_name = validate_template_name(template_name)
        if template_name is None:
            abort(404)

        if True:
            # Extract form data

            updated_data = {
                "url": request.form.get("url"),
                "frequency": request.form.get("frequency"),
                "timeout": request.form.get("timeout"),
                "notes": request.form.get("notes"),
                "popup_xpath": request.form.get("popup_xpath"),
                "dedicated_xpath": request.form.get("dedicated_xpath"),
                "callback_url": request.form.get("callback_url"),
                "proxy": request.form.get("proxy"),
                "rollback_frames": request.form.get("rollback_frames"),
                "groups": request.form.get("groups"),
                "object_filter": request.form.get("object_filter"),
                "object_confidence": request.form.get("object_confidence", 0.5),
                "motion": request.form.get("motion", 0.2),
                "invert": request.form.get("invert", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
                "dark": request.form.get("dark", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
                "headless": request.form.get("headless", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
                "stealth": request.form.get("stealth", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
                "browser": request.form.get("browser", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
                "livecaption": request.form.get("livecaption", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
                "danger": request.form.get("danger", "false").lower()
                in ["true", "1", "t", "y", "yes", "on"],
            }

            lremoves = []
            for lkey in updated_data:
                if updated_data.get(lkey) is None:
                    lremoves.append(lkey)
            for lkey in lremoves:
                del updated_data[lkey]

            # Validate and normalize the incoming form data. Any missing or
            # out-of-range values are replaced with sensible defaults. A
            # ``ValueError`` is raised when required fields are absent.
            try:
                updated_data = validate_update_data(updated_data)
            except ValueError as exc:
                if request.is_json:
                    return jsonify({"error": str(exc)}), 400
                flash(str(exc), "error")
                return redirect("/templates/" + template_name)

            # Update the template in your storage (e.g., JSON file, database)
            # This assumes you have a function to update templates
            template_manager.save_template(template_name, updated_data)

            # Stop the old scheduled job and generate a blank frame so the
            # updated template is clearly segmented in any compiled video.
            try:
                scheduling.scheduler.remove_job(template_name)
            except Exception:
                pass
            screenshots.create_blank_frame(template_name)
            template_manager.get_template(template_name)
            try:
                seconds = int(updated_data.get("frequency", 30 * 60))
                scheduling.scheduler.add_job(
                    func=scheduling.update_camera,
                    trigger="interval",
                    seconds=seconds,
                    args=[template_name, updated_data],
                    id=template_name,
                    replace_existing=True,
                )
            except Exception as e:
                logging.error("job schedule error: %s", e)

            if request.is_json:
                return jsonify({"message": "Template updated successfully!"})

            return redirect("/templates/" + template_name)

    @app.route("/discover", methods=["GET"])
    @login_required
    def discover_cameras_route():
        return render_template("discover.html", cameras=[])

    @app.route("/discover/scan", methods=["POST"])
    @login_required
    def discover_cameras_scan():
        cameras = camera_discovery.discover_cameras()
        return jsonify(cameras)

    @app.route("/discover/scan_stream")
    @login_required
    def discover_cameras_scan_stream():
        def generate():
            q = queue.Queue()
            # Provide the client with the number of discovery stages so it
            # can display a progress bar.
            q.put({"total": len(camera_discovery.get_discovery_stages())})

            sent = set()

            def progress(stage, count, new_cams):
                fresh = []
                for cam in new_cams:
                    key = (cam.get("ip"), cam.get("protocol"), cam.get("port"))
                    if key not in sent:
                        sent.add(key)
                        fresh.append(cam)
                q.put({"stage": stage, "count": count, "cameras": fresh})

            def run():
                camera_discovery.discover_cameras(progress_callback=progress)
                q.put({"done": True})

            thread = Thread(target=run, daemon=True)
            thread.start()

            while True:
                msg = q.get()
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("done"):
                    break

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    @app.route("/discover/add", methods=["POST"])
    @login_required
    def add_discovered_camera():
        data = request.form if request.form else request.get_json(force=True)
        name = data.get("name") or data.get("ip")
        protocol = data.get("protocol", "rtsp")
        port = int(data.get("port", 554))
        url = data.get("url") or f"{protocol}://{data.get('ip')}:{port}"
        template = {
            "name": name,
            "url": url,
            "frequency": data.get("frequency", 30),
            "timeout": data.get("timeout", 10),
        }
        template_manager.save_template(name, template)
        return jsonify({"status": "success"})

    @app.route("/status")
    @login_required
    def status():
        metrics = scheduling.get_system_metrics()
        return render_template("status.html", metrics=metrics)

    @app.route("/logs")
    @login_required
    def logs():
        return render_template("logs.html")

    @app.route("/stream_logs")
    @login_required
    def stream_logs():

        level = request.args.get("level")
        source = request.args.get("source")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        search = request.args.get("search")

        def generate():
            while True:
                # Get query parameters for filtering logs

                # Read and filter logs from memory
                logs = read_logs_from_memory(
                    level=level,
                    source=source,
                    start_date=start_date,
                    end_date=end_date,
                    search=search,
                )

                # Limit the number of logs sent to improve performance
                logs = logs[:50]

                yield f"data: {json.dumps(logs, default=str)}\n\n"
                time.sleep(1)  # Send updates every second

        return Response(generate(), mimetype="text/event-stream")

    @app.route("/sw.js")
    def service_worker():
        response = make_response(app.send_static_file("sw.js"))
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/toggle_scheduler", methods=["POST"])
    @login_required
    @profile_route("/toggle_scheduler")
    def toggle_scheduler():
        try:
            if scheduling.scheduler.running:
                scheduling.scheduler.shutdown(wait=True)
                return jsonify({"status": "stopped"})
            else:
                scheduling.scheduler.start()
                with app.app_context():
                    scheduling.scheduler.remove_all_jobs()
                    scheduling.schedule_crawlers()
                    scheduling.schedule_summarization()
                return jsonify({"status": "running"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/scheduler_status")
    @login_required
    @profile_route("/scheduler_status")
    def get_scheduler_status():
        return jsonify(
            {"status": "running" if scheduling.scheduler.running else "stopped"}
        )

    @app.route("/profiling")
    @login_required
    def profiling_data():
        return jsonify(get_latency_stats())
