import glob
import hashlib
import inspect
import io
import json
import logging
import os
import re
import sys
import time
import tempfile
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta
from functools import wraps
from threading import Lock, Thread

from flask import (
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
    stream_with_context,
)
from flask_login import logout_user, login_required
from PIL import Image
from sqlalchemy import text
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import app.config as config
from app.config import (
    API_KEY,
    SCREENSHOT_DIRECTORY,
    USER_NAME,
    USER_PASSWORD_HASH,
    VIDEO_DIRECTORY,
    VERSION
)
from app.utils import (
    scheduling,
    template_manager,
    video_archiver,
    screenshots
)
from app.utils.db import SessionLocal
from app.models.log import Log
from app.utils.scheduling import log_cache, log_cache_lock, start_log_caching

# Assuming 'app' is defined in __init__.py, import it here
from app import app

@app.route('/logs')
@login_required
def view_logs():
    try:
        # Get query parameters for filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        level = request.args.get('level')
        source = request.args.get('source')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')

        # Read and filter logs from memory
        logs = read_logs_from_memory(
            level=level,
            source=source,
            start_date=start_date,
            end_date=end_date,
            search=search
        )

        # Pagination logic
        total_logs = len(logs)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_logs = logs[start:end]

        return render_template('logs.html', logs=paginated_logs, page=page, per_page=per_page, total_logs=total_logs)
    except Exception as e:
        current_app.logger.error(f"Error in view_logs: {str(e)}")
        return render_template('logs.html', error=str(e)), 500

def restart_server():
    print("Restarting server...")

    def delayed_restart():
        time.sleep(1)  # 1-second delay
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Start the delayed restart in a separate thread
    restart_thread = Thread(target=delayed_restart)
    restart_thread.start()

# todo: add this to utils so it is not duplicated in utils/video_archiver.py
def validate_template_name(template_name: str):
    if template_name is None or not isinstance(template_name, str):
        return None

    # Strict whitelist of allowed characters
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.')

    # Check if all characters are in the allowed set
    if not all(char in allowed_chars for char in template_name):
        return None

    # Check length
    if len(template_name) == 0 or len(template_name) > 32:
        return None

    # Ensure the name doesn't start or end with a dash or underscore
    if template_name[0] in '-_.' or template_name[-1] in '-_.':
        return None
    if '..' in template_name:
        return None
    if '--' in template_name:
        return None
    if '__' in template_name:
        return None

    # Use secure_filename as an additional safety measure
    sanitized_name = secure_filename(template_name)

    # Ensure secure_filename didn't change the name (which would indicate it found something suspicious)
    if sanitized_name != template_name:
        return None

    return sanitized_name


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
        elif "logged_in" in session:
            # Check for session expiry
            expiry = session.get("expiry")
            if expiry and datetime.now() > datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S'):
                session.pop("logged_in", None)  # Clear session
                flash("Session expired. Please log in again.")
                return redirect(url_for("login", next=request.url))
            return f(*args, **kwargs)

        # Handle missing or invalid authentication
        else:
            if api_key:
                return jsonify({"error": "Invalid API key"}), 401
            else:
                return redirect(url_for("login", next=request.url))

    return decorated_function

# Function to read logs from the local text file and filter them based on query parameters
def read_logs_from_memory(level=None, source=None, start_date=None, end_date=None, search=None):
    global log_cache

    filtered_logs = []
    with log_cache_lock:
        for log in log_cache:
            # Apply filters if specified
            if (level and log["level"] != level) or (source and log["source"] != source):
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

        # TODO: blocklist some settings - set this somewhere
        lsettings_list = []
        blocks = ["SECRET_KEY", "USER_PASSWORD_HASH", "DATABASE_URL","VERSION"]
        for sl in settings_list:
            if re.findall(r"^[A-Z_]+?$", sl["name"]) and sl["name"] not in blocks:
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
                text("SELECT value FROM settings WHERE name = :name"),
                {"name": name}
        ).fetchone()
        if existing_setting:
            if existing_setting[0] != value:
                session.execute(
                    text("UPDATE settings SET value = :value WHERE name = :name"),
                    {"name": name, "value": value}
                )
                delta = True
                print("UPDATE", name, value, existing_setting)
        else:
            session.execute(
                text("INSERT INTO settings (name, value) VALUES (:name, :value)"),
                {"name": name, "value": value}
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


# TODO:
def generate_video_stream(video_path: str):

    # TODO: make sure it exists
    while True:
        with open(video_path, "rb") as video:
            chunk = video.read(1024 * 1024)  # Read 1 MB at a time
            while chunk:
                yield chunk
                chunk = video.read(1024 * 1024)
        #
        print(
            "sleeping...",
        )
        time.sleep(30)  # Wait for 5 minutes before streaming the video again


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


def generate(group=None, filename="latest_camera.png", rtsp=False):
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
                    and last_time
                    and time.time() - last_time < 1
                    and last_shot
                    and os.path.exists(last_shot)
                ):
                    # warning - todo, this needs to be completed still
                    try:
                        with Image.open(last_shot) as img:
                            img = resize_and_pad(img, (1280, 720))
                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG")
                            frame = buffer.getvalue()
                    except Exception:
                        pass  # TODO logging
                else:
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
                            with Image.open(most_recent_file) as img:
                                img = resize_and_pad(img, (1280, 720))
                                buffer = io.BytesIO()
                                img.save(buffer, format="JPEG")
                                frame = buffer.getvalue()
                                # file sizes the same size?  maybe just touch the file instead?

                                # write this to a file! cache it.  read that cache if possible
                                with open(last_path, "wb") as f:
                                    f.write(frame)
                                # only do this if the files are different.  otherwise, just freshen up maybe?
                                os.rename(last_path, last_path.replace(".tmp", ""))
                        except Exception:
                            # print(" warning: png error", e)
                            pass

        if frame:
            if rtsp:
                # For RTSP, we need to add RTP headers and packetize the frame
                # This is a simplified version and may need to be adjusted based on your exact requirements
                rtp_header = b"\x80\x60\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
                yield rtp_header + frame
            else:
                yield b"--" + boundary + b"\r\n"
                yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n"
        if time.time() - ltime > 1:
            continue
        time.sleep(1 - (time.time() - ltime))

def allowed_filename(filename: str) -> bool:

    if '..' in filename:
        return False

    if re.findall(r'^[a-zA-Z0-9\.\-_]+?$', filename):

        return True

    return False

def init_routes(app):
    global login_attempts
    # get_active_groups()

    @app.context_processor
    def inject_footer_data():
        return dict(
            VERSION=VERSION
        )

    # Add a new route for the extended health check
    @app.route('/health')
    @login_required
    def health_check():

        scheduler_status = 'failed'
        free_gb = 0

        metrics = scheduling.get_system_metrics()

        # Define thresholds for nominal performance
        cpu_threshold = 80  # 80% CPU usage
        memory_threshold = 80  # 80% memory usage
        thread_threshold = 100  # 100 threads # should be tied to the thread count in the config, right? 
        open_file_threshold = 1024 # thats a lot
        disk_threshold = 95 # almost full 

        # Check if metrics are nominal
        is_nominal = (
            metrics['cpu_usage'] < cpu_threshold and
            metrics['memory_usage'] < memory_threshold and
            metrics['thread_count'] < thread_threshold and
            metrics['open_files'] < open_file_threshold and
            metrics['disk_usage'] < disk_threshold
        )

        try:
            #0h 1m 6s
            if len(metrics['uptime']) < 9: # first ten seconds... 
                is_nominal = False
        except Exception as e:
            is_nominal = False

        ###### 
        #  consider rolling these into the metrics
        try:
            # Check database connection
            session = SessionLocal()
            session.execute(text("SELECT 1"))
            session.close()
            db_status = 'connected'
        except Exception as e:
            is_nominal = False
            pass # its for the healthcheck...
        if db_status != 'connected':
            is_nominal = False

        try:
            # Check if scheduler is running
            scheduler_status = "running" if scheduling.scheduler.running else "stopped"
        except Exception as e:
            is_nominal = False
            pass # its for the healthcheck...
        if scheduler_status != 'running':
            is_nominal = False

        #
        ###### 

        return jsonify({
            'status': 'healthy' if is_nominal else 'degraded',
            'metrics': metrics,
            'nominal': is_nominal,
            "database": db_status,
            "scheduler": scheduler_status,
            "free_disk_space_gb": free_gb
        }), 200 # always return 200, but might be degraded.


    @app.route('/api/discover')
    def api_discover():
        api_info = {
            "version": "1.0",
            "endpoints": [
                {
                    "path": "/health",
                    "method": "GET",
                    "description": "Check the health status of the API",
                    "authentication_required": False
                },
                {
                    "path": "/api/discover",
                    "method": "GET",
                    "description": "Get information about available API endpoints",
                    "authentication_required": False
                },
                {
                    "path": "/login",
                    "method": "GET, POST",
                    "description": "User login endpoint",
                    "authentication_required": False
                },
                {
                    "path": "/logout",
                    "method": "GET",
                    "description": "User logout endpoint",
                    "authentication_required": True
                },
                {
                    "path": "/",
                    "method": "GET",
                    "description": "Main index page",
                    "authentication_required": True
                },
                {
                    "path": "/templates",
                    "method": "GET, POST, DELETE",
                    "description": "Manage templates",
                    "authentication_required": True
                },
                {
                    "path": "/settings",
                    "method": "GET, POST",
                    "description": "Manage application settings",
                    "authentication_required": True
                }
            ]
        }
        return jsonify(api_info), 200


    @app.route("/login", methods=["GET", "POST"])
    def login():
        ip_address = request.remote_addr
        now = datetime.now()

        # Check if the IP address is locked out
        if (
            ip_address in login_attempts
            and login_attempts[ip_address]["locked_until"] > now
        ):
            return "Too many failed attempts. Please try again later.", 429

        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]

            if username == USER_NAME and check_password_hash(
                USER_PASSWORD_HASH, password
            ):
                session["logged_in"] = True
                login_attempts.pop(
                    ip_address, None
                )  # Reset attempts on successful login
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

                flash("Invalid username or password")
        return render_template("login.html")

    @app.route("/help")
    @login_required
    def help_page():
        return render_template("help.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.pop("logged_in", None)
        flash("You have been logged out successfully.", "success")
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        # TODO: maybe include the template details
        return render_template("index.html")

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

        # Check if the template exists
        print("WARNING BRPKEN!")
        ltemplate = template_manager.get_template(template_name)
        if ltemplate is None:
            return jsonify({"status": "error", "message": "Template not found"}), 404
        template_name = ltemplate.get("name")  # todo...

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
            timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
            filename = f"{template_name}_{timestamp}.png.tmp"
            output_path = os.path.join(SCREENSHOT_DIRECTORY, template_name, filename)
            #if not os.path.normpath(output_path).startswith(SCREENSHOT_DIRECTORY):
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

        if os.path.exists(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                SCREENSHOT_DIRECTORY,
                "latest_camera.png",
            )
        ):
            # TODO: check for file integrity
            return send_file(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..",
                    SCREENSHOT_DIRECTORY,
                    "latest_camera.png",
                )
            )

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
        for template in sorted_templates:
            name = secure_filename(template.get("name"))
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                SCREENSHOT_DIRECTORY,
                name,
            )
            lfiles = [f for f in glob.glob(path + "/*.png") if os.path.isfile(f)]
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
        return send_file(last_file)  # better than nothing

    @app.route("/test.rtsp", methods=["OPTIONS", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN"])
    def handle_rtsp():
        global rtsp_sessions

        session_id = request.headers.get("Session", str(uuid.uuid4()))
        cseq = request.headers.get("CSeq", "0")

        if request.method == "OPTIONS":
            return Response(
                "Public: OPTIONS, DESCRIBE, SETUP, TEARDOWN, PLAY",
                headers={"CSeq": cseq},
            )

        elif request.method == "DESCRIBE":
            sdp = (
                "v=0\r\n"
                "o=- 0 0 IN IP4 127.0.0.1\r\n"
                "s=Glimpser RTSP Stream\r\n"
                "t=0 0\r\n"
                "m=video 0 RTP/AVP 96\r\n"
                "a=rtpmap:96 H264/90000\r\n"
                "a=control:streamid=0\r\n"
            )
            return Response(
                sdp,
                mimetype="application/sdp",
                headers={"CSeq": cseq, "Content-Base": request.url},
            )

        elif request.method == "SETUP":
            if session_id not in rtsp_sessions:
                rtsp_sessions[session_id] = {"state": "READY"}
            transport = request.headers.get("Transport", "")
            return Response(
                headers={
                    "CSeq": cseq,
                    "Session": session_id,
                    "Transport": transport,
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
        return Response(
            generate(group=group, filename="latest_camera.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/motion.mjpg", methods=["GET"])
    def motion_mjpg():
        group = request.args.get("group")
        return Response(
            generate(group=group, filename="last_motion.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/caption.mjpg", methods=["GET"])
    def caption_mjpg():
        group = request.args.get("group")
        print("last caption")
        return Response(
            generate(group=group, filename="last_caption.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/motion_caption.mjpg", methods=["GET"])
    def motion_caption_mjpg():
        group = request.args.get("group")
        print("last motion caption")
        return Response(
            generate(group=group, filename="last_motion_caption.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/rtsp_stream")
    def rtsp_stream():
        session_id = request.args.get("session")
        if session_id not in rtsp_sessions or rtsp_sessions[session_id]["state"] != "PLAYING":
            abort(400, "Invalid session or session not in PLAYING state")
        return Response(
            generate(rtsp=True),
            mimetype="application/x-rtp"
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
        return send_file(video_path)
        # TODO: implement slowstreaming and continuous streaming
        # return Response(stream_with_context(generate_video_stream(video_path)), mimetype='video/mp4')

    @app.route("/stream.m3u8")
    @login_required
    def playlist_m3u8():
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", VIDEO_DIRECTORY
        )

        # Check if the video directory exists
        if not os.path.exists(path):
            abort(404)

        # Generate playlist content
        playlist_content = "#EXTM3U\n"
        playlist_content += "#EXT-X-VERSION:3\n"
        playlist_content += "#EXT-X-TARGETDURATION:10\n"  # Assuming each segment is up to 10 seconds
        playlist_content += "#EXT-X-MEDIA-SEQUENCE:0\n"

        templates = template_manager.get_templates()
        # Sort templates by 'last_video_time' descending
        sorted_templates = sorted(
            templates.items(),
            key=lambda x: (x[1].get("last_video_time", 0) or 0),
            reverse=True,
        )

        for camera_id, template in sorted_templates:
            camera_name = template.get("name")
            # Assuming the MP4 file is the segment
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

        # Specify the directory containing the .jl files
        directory = "data/summaries/"

        # Get all files in the directory
        files = os.listdir(directory)

        # Filter out only .jl files and sort them by last modified time in descending order
        jl_files = sorted(
            [file for file in files if file.endswith(".jl")],
            key=lambda x: os.path.getmtime(os.path.join(directory, x)),
            reverse=True,
        )

        # Load entries from the most recent 5 .jl files
        entries = []
        for file in jl_files[:5]:
            file_path = os.path.join(directory, file)
            with open(file_path, "r") as f:
                try:
                    data = json.load(f)
                    entries.append(data)
                except Exception:
                    pass

        # Get a list of active cameras (with updates within the last 1 day)
        return render_template(
            "captions.html",
            template_details=template_manager.get_templates(),
            lcaptions=entries,
        )

    @app.route("/live")
    @login_required
    def live():
        # Get a list of active cameras (with updates within the last 1 day)
        return render_template(
            "live.html", template_details=template_manager.get_templates()
        )

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
            (f for f in os.listdir(path) if f.endswith('.png')),
            key=lambda f: os.path.getmtime(os.path.join(path, f))
        )

        if latest_file:
            return send_file(os.path.join(path, latest_file), mimetype='image/png')

        abort(404)

    # TODO: extend this for groups
    @app.route("/last_teaser")
    @login_required
    def serve_teaser():
        """
        Serve the group teaser video
        """
        # Placeholder logic to serve the screenshot
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", VIDEO_DIRECTORY
        )
        if not os.path.exists(path):
            abort(404)

        if os.path.exists(path + "/all_in_process.mp4"):
            return send_file(path + "/all_in_process.mp4")

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
        lfiles.sort(key=os.path.getmtime)
        if len(lfiles) > 0:
            return send_file(lfiles[-1])

        abort(404)

    @app.route("/compile_teaser", methods=["GET"]) # todo: should probably be post? 
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

        print("TODO: rewrite")
        templates = template_manager.get_templates()
        if templates.get(template_name) is None:
            abort(404)

        # TODO: add more handling around this
        # Save the uploaded file to a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            image_file.save(temp_file.name)
            # Call the update_camera function with the temporary file path
            scheduling.update_camera(
                template_name, templates.get(template_name), image_file=temp_file.name
            )
            # potentially trigger motion too...

        # Clean up the temporary file
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

        # TODO: consider adding motion control
        scheduling.update_camera(template_name, templates.get(template_name))
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
            if template_manager.save_template(
                template_name, data
            ):
                return jsonify({"status": "success", "message": "Template saved"})

        elif request.method == "GET":
            group = request.args.get("group")
            search_query = request.args.get("search", "").lower()
            templates = template_manager.get_templates()

            filtered_templates = {}
            for name, template in templates.items():
                template_groups = template.get("groups", "").split(",")
                if (group == "all" or group in template_groups) and \
                   (not search_query or
                    search_query in name.lower() or
                    any(search_query in g.lower() for g in template_groups)):
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

    @app.route("/screenshots/<string:name>/<string:filename>")
    @login_required
    def uploaded_file(name: TemplateName, filename: str):
        template_name = validate_template_name(name)
        if template_name is None:
            abort(404)
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", SCREENSHOT_DIRECTORY, template_name
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
                text("DELETE FROM settings WHERE name = :name"),
                {"name": name}
            )
            session.commit()
        finally:
            session.close()

        return True

    @app.route("/videos/<string:name>/<string:filename>")
    @login_required
    def view_video(name: TemplateName, filename: str):
        template_name = validate_template_name(name)
        if template_name is None:
            abort(404)
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", VIDEO_DIRECTORY, template_name
        )
        if not os.path.exists(path):
            abort(404)

        return send_from_directory(path, filename)


    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            email_settings = [
                    "EMAIL_ENABLED", "EMAIL_SENDER", "EMAIL_RECIPIENTS",
                    "EMAIL_SMTP_SERVER", "EMAIL_SMTP_PORT", "EMAIL_USE_TLS",
                    "EMAIL_USERNAME", "EMAIL_PASSWORD"
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
            else:
                for name, value in request.form.items():
                    if name not in ["action", "new_name", "new_value", "name_to_delete"] + email_settings:
                        update_setting(name, value)
            return redirect(url_for("settings"))

        settings = get_all_settings()
        return render_template("settings.html", settings=settings)

    # TODO: this has been refactored to health instead.. please update
    @app.route('/system_metrics')
    def system_metrics():
        return jsonify(scheduling.get_system_metrics())

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

            # TODO: validate

            if updated_data.get("rollback_frames") == "":
                updated_data["rollback_frames"] = 0
            if updated_data.get("timeout") == "":
                updated_data["timeout"] = 30
            if updated_data.get("frequency") == "":
                updated_data["frequency"] = 30

            # Update the template in your storage (e.g., JSON file, database)
            # This assumes you have a function to update templates
            template_manager.save_template(template_name, updated_data)

            # TODO: stop the old job.  reschedule the camera
            # TODO: generate a blank template and insert it (like a movie reel type of thing)
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
                print("job schedule error:", e)
                # logging.error(f"Error scheduling job for {name}: {e}")

            if request.is_json:
                return jsonify({"message": "Template updated successfully!"})

            return redirect("/templates/" + template_name)

    @app.route('/logs')
    @login_required
    def view_logs():
        # Get query parameters for filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        level = request.args.get('level')
        source = request.args.get('source')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')

        # Read and filter logs from memory
        logs = read_logs_from_memory(
            level=level,
            source=source,
            start_date=start_date,
            end_date=end_date,
            search=search
        )

        # Pagination logic
        total_logs = len(logs)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_logs = logs[start:end]

        return render_template('logs.html', logs=paginated_logs, page=page, per_page=per_page, total_logs=total_logs)

    @app.route("/status")
    @login_required
    def status():
        metrics = scheduling.get_system_metrics()
        templates = template_manager.get_templates()

        camera_schedules = []
        for name, template in templates.items():
            last_screenshot_time = template.get('last_screenshot_time')
            frequency = int(template.get('frequency', 30))  # Default to 30 minutes if not set

            if last_screenshot_time:
                last_screenshot = datetime.strptime(last_screenshot_time, "%Y-%m-%d %H:%M:%S")
                next_screenshot = last_screenshot + timedelta(minutes=frequency)
            else:
                last_screenshot = None
                next_screenshot = None

            thumbnail_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name), 'latest_camera.png')
            thumbnail_url = url_for('uploaded_file', name=name, filename='latest_camera.png') if os.path.exists(thumbnail_path) else None

            camera_schedules.append({
                'name': name,
                'last_screenshot': last_screenshot,
                'next_screenshot': next_screenshot,
                'thumbnail_url': thumbnail_url,
                'template_url': url_for('template_details', template_name=name)
            })

        return render_template("status.html", metrics=metrics, camera_schedules=camera_schedules)

