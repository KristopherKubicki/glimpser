# config.py

import argparse
import importlib.util
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
from importlib.metadata import PackageNotFoundError, version
from ipaddress import ip_network
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

_ffmpeg_spec = importlib.util.spec_from_file_location(
    "app.utils.ffmpeg_setup",
    Path(__file__).resolve().parent / "utils" / "ffmpeg_setup.py",
)
ffmpeg_setup = importlib.util.module_from_spec(_ffmpeg_spec)
_ffmpeg_spec.loader.exec_module(ffmpeg_setup)

_SKIP_DB_INIT = os.getenv("GLIMPSER_SKIP_DB_INIT") == "1"

_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    """Load ``.env`` variables once per process.

    ``dotenv`` silently succeeds if called multiple times but repeating the
    operation can be wasteful when this module is imported frequently. This
    helper keeps track of whether variables have been loaded already and skips
    re-loading on subsequent calls.
    """
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        load_dotenv(find_dotenv())
        _DOTENV_LOADED = True


# Load variables from a ``.env`` file if present.  Using ``_load_dotenv_once``
# ensures we do not re-read the file unnecessarily should this module somehow
# be imported more than once.
_load_dotenv_once()


# Parse command line arguments when executed directly
def _parse_cli_args():
    """Return parsed command line options.

    The arguments include ``--db-path``, ``--log-path`` and
    ``--backup-path`` when the module is executed directly.

    Returns:
        argparse.Namespace: The populated arguments namespace.
    """

    parser = argparse.ArgumentParser(description="Glimpser configuration")
    parser.add_argument("--db-path", help="Path to the SQLite database file")
    parser.add_argument("--log-path", help="Path to the log file")
    parser.add_argument(
        "--backup-path", help="Path to the configuration backup JSON file"
    )
    return parser.parse_args()


_cli_args = _parse_cli_args() if __name__ == "__main__" else None

# Resolve paths relative to the project root when a relative path is provided
_BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    _cli_args.db_path
    if _cli_args and _cli_args.db_path
    else os.getenv("GLIMPSER_DATABASE_PATH", "data/glimpser.db")
)
LOGGING_PATH = (
    _cli_args.log_path
    if _cli_args and _cli_args.log_path
    else os.getenv("GLIMPSER_LOGGING_PATH", "logs/glimpser.log")
)

# Ensure paths remain valid if the working directory changes.
_db_rel = Path(DATABASE_PATH)
DATABASE_PATH = str(_db_rel if _db_rel.is_absolute() else _BASE_DIR / _db_rel)
_log_rel = Path(LOGGING_PATH)
LOGGING_PATH = str(_log_rel if _log_rel.is_absolute() else _BASE_DIR / _log_rel)
# Ensure the backup file lives inside the project directory unless an absolute
# path is provided. This avoids errors when the working directory changes.
_backup_env = os.getenv("GLIMPSER_BACKUP_PATH", "data/config_backup.json")
_backup_raw = (
    _cli_args.backup_path if _cli_args and _cli_args.backup_path else _backup_env
)
_backup_path = Path(_backup_raw)
BACKUP_PATH = str(
    _backup_path if _backup_path.is_absolute() else _BASE_DIR / _backup_path
)

# ``SessionLocal`` and ``_engine`` are created lazily and cached so repeated
# imports or function calls don't open additional connections.  Tests may patch
# ``SessionLocal`` to supply a fake sessionmaker.
SessionLocal = None
_engine = None


def _get_session():
    """Return a new database session.

    When ``SessionLocal`` has been patched (e.g. during testing) the patched
    callable is used.  Otherwise the engine and sessionmaker are created on
    first use and cached so repeated imports don't create multiple engines.
    """

    global _engine, SessionLocal

    if _SKIP_DB_INIT:

        class _DummyResult:
            def fetchone(self):
                return None

            def fetchall(self):
                return []

        class _DummySession:
            def execute(self, *args, **kwargs):
                return _DummyResult()

            def commit(self):
                pass

            def close(self):
                pass

        return _DummySession()

    if SessionLocal is not None:
        return SessionLocal()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    effective_db_path = os.getenv("GLIMPSER_DATABASE_PATH", DATABASE_PATH)
    needs_engine = _engine is None
    if not needs_engine:
        try:
            needs_engine = str(_engine.url) != f"sqlite:///{effective_db_path}"
        except Exception:
            needs_engine = True

    if needs_engine:
        db_dir = os.path.dirname(effective_db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _engine = create_engine(f"sqlite:///{effective_db_path}")
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    return SessionLocal()


def get_setting(name, default=None):
    """Return a setting from the environment or the database."""
    env_val = os.getenv(name)
    if env_val is not None:
        return env_val

    session = _get_session()
    try:
        result = session.execute(
            text("SELECT value FROM settings WHERE name = :name"),
            {"name": name},
        ).fetchone()
        return result[0] if result else default
    except (OperationalError, sqlite3.OperationalError) as e:
        if "no such table" in str(e):
            # This is ok on first run when the DB is empty.
            logging.debug("settings table does not exist yet")
        else:
            logging.warning("initialization error %s", e)
    except SQLAlchemyError as e:
        logging.warning("database error %s", e)
    except Exception:  # pragma: no cover - unexpected errors
        logging.exception("unexpected error while fetching setting")
        raise
    finally:
        session.close()

    return default


def backup_config() -> bool:
    """Back up database settings to ``BACKUP_PATH``.

    Returns:
        bool: ``True`` when the file was written successfully,
        ``False`` otherwise.
    """

    session = _get_session()
    success = True
    try:
        settings = session.execute(text("SELECT name, value FROM settings")).fetchall()
        config_dict = {name: value for name, value in settings}
        os.makedirs(os.path.dirname(BACKUP_PATH), exist_ok=True)
        with open(BACKUP_PATH, "w") as f:
            json.dump(config_dict, f)
    except (OperationalError, SQLAlchemyError, sqlite3.OperationalError, OSError) as e:
        logging.warning("backup failed: %s", e)
        success = False
    except Exception:  # pragma: no cover - unexpected errors
        logging.exception("unexpected error during backup")
        raise
    finally:
        session.close()
    return success


def restore_config():
    """Restore configuration from ``BACKUP_PATH`` if it exists."""

    if os.path.exists(BACKUP_PATH):
        with open(BACKUP_PATH) as f:
            config_dict = json.load(f)

        session = _get_session()
        try:
            for name, value in config_dict.items():
                session.execute(
                    text(
                        "INSERT OR REPLACE INTO settings (name, value) VALUES (:name, :value)"
                    ),
                    {"name": name, "value": value},
                )
            session.commit()
        finally:
            session.close()


def sync_version(pkg_version: str) -> None:
    """Update the VERSION row when it doesn't match ``pkg_version``."""
    if os.getenv("VERSION"):
        return

    session = _get_session()
    try:
        existing = session.execute(
            text("SELECT value FROM settings WHERE name = :name"),
            {"name": "VERSION"},
        ).fetchone()
        if existing is None or existing[0] != pkg_version:
            session.execute(
                text(
                    "INSERT INTO settings (name, value) VALUES (:name, :value) "
                    "ON CONFLICT(name) DO UPDATE SET value = :value"
                ),
                {"name": "VERSION", "value": pkg_version},
            )
            session.commit()
    except (OperationalError, sqlite3.OperationalError) as e:
        if "no such table" in str(e):
            logging.debug("settings table does not exist yet")
        else:
            logging.warning("initialization error %s", e)
    except SQLAlchemyError as e:
        logging.warning("database error %s", e)
    except Exception:  # pragma: no cover - unexpected errors
        logging.exception("unexpected error during version sync")
        raise
    finally:
        session.close()


SCHEDULER_API_ENABLED = get_setting("SCHEDULER_API_ENABLED", "True") == "True"
REQUEST_VERIFY_SSL = get_setting("REQUEST_VERIFY_SSL", "False") == "True"

# be careful when mounting network devices
SCREENSHOT_DIRECTORY = "data/screenshots/"
_shot_rel = Path(SCREENSHOT_DIRECTORY)
SCREENSHOT_DIRECTORY = str(
    _shot_rel if _shot_rel.is_absolute() else _BASE_DIR / _shot_rel
)
VIDEO_DIRECTORY = "data/video/"
CLIPS_DIRECTORY = "data/clips/"
SUMMARIES_DIRECTORY = "data/summaries/"
DOCS_DIRECTORY = "docs"

# Load settings from the database
UA = get_setting(
    "UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
)
LANG = get_setting("LANG", "en-US")
TZ = get_setting("TZ", "UTC")
try:
    _PKG_VERSION = version("glimpser")
except PackageNotFoundError:
    _PKG_VERSION = "0.2.9"
sync_version(_PKG_VERSION)
# Default to the package version if not overridden in the database
VERSION = get_setting("VERSION", _PKG_VERSION)
NAME = get_setting("NAME", "glimpser")
NAV_ICON = get_setting("NAV_ICON", "img/glimpser_small.png")
HOST = get_setting("HOST", "0.0.0.0")
PORT = int(get_setting("PORT", 8082))
DANGER_PORT = int(get_setting("DANGER_PORT", 9222))
HTTPS_ENABLED = get_setting("HTTPS_ENABLED", "False") == "True"
HTTPS_PORT = int(get_setting("HTTPS_PORT", 8443))
HTTPS_ONLY = get_setting("HTTPS_ONLY", "False") == "True"
HTTPS_SELF_SIGNED = get_setting("HTTPS_SELF_SIGNED", "True") == "True"
HTTPS_CERT_PATH = get_setting("HTTPS_CERT_PATH", "data/certs/glimpser.crt")
HTTPS_KEY_PATH = get_setting("HTTPS_KEY_PATH", "data/certs/glimpser.key")
HTTPS_CERT_HOSTNAMES = get_setting("HTTPS_CERT_HOSTNAMES", "")
_https_cert_rel = Path(HTTPS_CERT_PATH)
HTTPS_CERT_PATH = str(
    _https_cert_rel if _https_cert_rel.is_absolute() else _BASE_DIR / _https_cert_rel
)
_https_key_rel = Path(HTTPS_KEY_PATH)
HTTPS_KEY_PATH = str(
    _https_key_rel if _https_key_rel.is_absolute() else _BASE_DIR / _https_key_rel
)
ENFORCE_DOMAIN_IN_HOST = get_setting("ENFORCE_DOMAIN_IN_HOST", "False") == "True"
DEBUG = get_setting("DEBUG", "False") == "True"
# Provide a separate attribute for runtime checks
DEBUG_MODE = DEBUG
LOW_CPU_MODE = get_setting("LOW_CPU_MODE", "False") == "True"
_max_workers_cfg = int(get_setting("MAX_WORKERS", 8))
if LOW_CPU_MODE:
    # Keep a single-digit worker pool to avoid CPU saturation on weaker hosts.
    _low_cpu_cap = max(1, min(2, (os.cpu_count() or 1) // 2))
    MAX_WORKERS = max(1, min(_max_workers_cfg, _low_cpu_cap))
else:
    MAX_WORKERS = _max_workers_cfg

# Thresholds
MAX_RAW_DATA_SIZE = int(get_setting("MAX_RAW_DATA_SIZE", 500 * 1024 * 1024))  # 500 MB
MAX_IMAGE_RETENTION_AGE = int(get_setting("MAX_IMAGE_RETENTION_AGE", 8))
MAX_VIDEO_RETENTION_AGE = int(get_setting("MAX_VIDEO_RETENTION_AGE", 365))
MAX_COMPRESSED_VIDEO_AGE = int(get_setting("MAX_COMPRESSED_VIDEO_AGE", 7))  # days
MAX_IN_PROCESS_VIDEO_SIZE = int(
    get_setting("MAX_IN_PROCESS_VIDEO_SIZE", 100 * 1024 * 1024)
)  # 100 MB
ARCHIVE_BATCH_SIZE = int(get_setting("ARCHIVE_BATCH_SIZE", 25))
ARCHIVE_INTERVAL_MINUTES = int(get_setting("ARCHIVE_INTERVAL_MINUTES", 1))
LAN_OFFLINE_DISABLE_ERRORS = int(get_setting("LAN_OFFLINE_DISABLE_ERRORS", 6))
LAN_OFFLINE_DISABLE_WINDOW_MINUTES = int(
    get_setting("LAN_OFFLINE_DISABLE_WINDOW_MINUTES", 60)
)
LAN_OFFLINE_BACKOFF_SECONDS = int(get_setting("LAN_OFFLINE_BACKOFF_SECONDS", 1800))
RTSP_PREFLIGHT_FAIL_THRESHOLD = int(get_setting("RTSP_PREFLIGHT_FAIL_THRESHOLD", 3))
RTSP_PREFLIGHT_FAIL_WINDOW_SECONDS = int(
    get_setting("RTSP_PREFLIGHT_FAIL_WINDOW_SECONDS", 900)
)
RTSP_PREFLIGHT_BACKOFF_SECONDS = int(
    get_setting("RTSP_PREFLIGHT_BACKOFF_SECONDS", 3600)
)

LOG_LEVEL = get_setting("LOG_LEVEL", "WARN")
FLASK_LOG_LEVEL = get_setting("FLASK_LOG_LEVEL", LOG_LEVEL)
LOG_RATE_LIMIT_SEC = int(get_setting("LOG_RATE_LIMIT_SEC", 60))
LOG_COLOR = get_setting("LOG_COLOR", "True") == "True"

# Session security settings
SESSION_COOKIE_SECURE = get_setting("SESSION_COOKIE_SECURE", "True") == "True"
SESSION_COOKIE_HTTPONLY = get_setting("SESSION_COOKIE_HTTPONLY", "True") == "True"
SESSION_TIMEOUT_MINUTES = int(get_setting("SESSION_TIMEOUT_MINUTES", 30))
AUTO_LOGIN_DAYS = int(get_setting("AUTO_LOGIN_DAYS", 30))
# Skip login for these networks when not accessing admin pages
_login_subnets_raw = get_setting("SKIP_LOGIN_SUBNETS", "")
SKIP_LOGIN_SUBNETS = []
for _sub in [s.strip() for s in _login_subnets_raw.split(",") if s.strip()]:
    try:
        SKIP_LOGIN_SUBNETS.append(ip_network(_sub))
    except ValueError:
        logging.warning("Invalid subnet in SKIP_LOGIN_SUBNETS: %s", _sub)
LAN_GUEST_MODE = get_setting("LAN_GUEST_MODE", "full").lower()

# Clock configuration
CLOCK_OVERLAY = get_setting("CLOCK_OVERLAY", "False") == "True"
CLOCK_DIGITAL = get_setting("CLOCK_DIGITAL", "False") == "True"
CLOCK_NAVBAR = get_setting("CLOCK_NAVBAR", "True") == "True"

# Load settings from the database
SECRET_KEY = get_setting("SECRET_KEY", "default_secret_key")
USER_NAME = get_setting("USER_NAME", "admin")
API_KEY = get_setting("API_KEY", "")
SSO_TOKEN = get_setting("SSO_TOKEN", "")
SSO_USERNAME = get_setting("SSO_USERNAME", USER_NAME)
CHATGPT_KEY = get_setting("CHATGPT_KEY", "")  # maybe generalize as LLM_KEY ?
RECOVERY_SEARCH_MODEL = get_setting("RECOVERY_SEARCH_MODEL", "gpt-5-mini")

ALLOWED_LLM_MODELS = [
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4",
]

LLM_MODEL_VERSION = get_setting("LLM_MODEL_VERSION", "gpt-5-mini")

LOCAL_LLM_FALLBACK = get_setting("LOCAL_LLM_FALLBACK", "False") == "True"
LOCAL_LLM_BASE_URL = get_setting("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
LOCAL_LLM_VISION_MODEL = get_setting("LOCAL_LLM_VISION_MODEL", "moondream:latest")
LOCAL_LLM_TEXT_MODEL = get_setting("LOCAL_LLM_TEXT_MODEL", "qwen2.5:3b")
LOCAL_LLM_TIMEOUT_SECONDS = int(get_setting("LOCAL_LLM_TIMEOUT_SECONDS", 90))

# Keep local helper defaults in sync with configured settings.
os.environ.setdefault("LOCAL_LLM_BASE_URL", LOCAL_LLM_BASE_URL)
os.environ.setdefault("LOCAL_LLM_TIMEOUT_SECONDS", str(LOCAL_LLM_TIMEOUT_SECONDS))

if LLM_MODEL_VERSION == "gpt-4.1-mini":
    logging.warning("Deprecated LLM model gpt-4.1-mini; defaulting to gpt-5-mini.")
    LLM_MODEL_VERSION = "gpt-5-mini"

if LLM_MODEL_VERSION not in ALLOWED_LLM_MODELS:
    raise ValueError(f"Invalid LLM model: {LLM_MODEL_VERSION}")

# note that $datetime is a special keyword that will be replaced with the datetime in iso Z format
LLM_SUMMARY_PROMPT = get_setting(
    "LLM_SUMMARY_PROMPT",
    "Return one single line of plain text—no line breaks, numbers, or bullet lists—beginning with a brief greeting plus today’s date, local time, and Chicago temperature, then densely packed clauses separated by “ | ”, each clause giving grouped insights, forecasts, and local take-aways drawn from the logs and any provided history; mark critical items with ⚠️, routine-but-watchworthy items with ℹ️ (info symbol), and resolved items with ✔️; weave a coherent bigger story rather than camera-by-camera notes, avoid repetition, drop boiler-plate, use precise technical language, and include uncommon insights or likely next events whenever possible; if nothing is noteworthy output exactly “All systems nominal — no actionable items.” The time is $datetime UTC.",
    # "Below are caption logs from multiple live sources. Produce a 10-line technical digest for a highly educated Chicago-area listener who glances for <30 s. Format: line 0 → greeting + date/time + current temperature + one-sentence “big picture”; lines 1-9 → plain-text bullets of ≤90 chars each, no timestamps, each tagged with ⚠️ for immediate action, ℹ️ for watch/interesting, ✔️ for resolved/nominal. Group related items logically; emphasise local (Chicago/Lincolnwood/Kenosha), include concrete facts (counts, magnitudes, street names, runways, K-index, etc.), omit boiler-plate and repeated info unless it’s a new alert. Tie items into a bigger narrative (weather → transit → power → cosmic events) rather than a camera list. If nothing merits mention, output exactly “All systems nominal — no actionable items.” The time is $datetime UTC.",
    # "Summarize the following logs into a concise, technical transcript. Focus on providing clear, actionable insights and key takeaways. Keep the summary brief and organized, with one line per segment, separated by newlines. Start with a brief overview, including any major events or trends. Prioritize clarity and relevance, ensuring the summary is easy to understand and useful for decision-making. Avoid repetition unless necessary. Conclude with a brief summary or closing note. The time is $datetime.",
)

LLM_CAPTION_PROMPT = get_setting(
    "LLM_CAPTION_PROMPT",
    "Examine the image carefully, then reply in two paragraphs only: (1) a punchy headline of ≤ 10 words that captures the single most urgent, unusual, or otherwise news-worthy element the user glancing for three seconds needs to notice; (2) one or two sharply written sentences that expand on that element with concrete specifics—names, counts, street or airport identifiers, magnitudes, colour codes, timestamps, likely impact, or next action—strictly based on visual evidence and the accompanying user question. Skip generic scene-setting, boiler-plate weather phrases, interface chrome, or guessing. If the frame is blank, frozen, unreadable, or unchanged since the previous image, respond only with the word **UNREADABLE**. Do not output anything else. The time is $datetime UTC.",
    # Provide a concise, insightful observation about this image. Focus on unique or significant aspects. Limit your response to 16 words or less. Do not describe the scene, describe the anomalies. Do not be concerned about timestamp issues (the image may have local and UTC timestamps on it). Provide a concise caption in 10 words o less, focusing only on the noteable aspects.  Avoid general descriptions. Keep it short!  Then, on a newline, write a couple sentences with a more detailed description. The time is $datetime UTC
    # "Write a concise caption that highlights the most significant or unique aspect of this image in 10 words or less. Avoid general descriptions, and focus on noteworthy details or anomalies. Then, provide a brief, more detailed description in a couple of sentences. The time is $datetime UTC.",
)

# FFMPEG/FFPROBE path settings
_ffmpeg_default = ffmpeg_setup.get_ffmpeg_path() or "ffmpeg"
FFMPEG_PATH = get_setting("FFMPEG_PATH", _ffmpeg_default)
FFPROBE_PATH = get_setting("FFPROBE_PATH", "ffprobe")


def _machine_supports_hwaccel() -> bool:
    """Return ``True`` if GPU devices appear to be available."""

    return os.path.exists("/dev/dri") or shutil.which("nvidia-smi") is not None


def _ffmpeg_supports_hwaccel() -> bool:
    """Return ``True`` if ``ffmpeg`` lists any hardware acceleration methods."""

    try:
        output = subprocess.check_output(
            [FFMPEG_PATH, "-hwaccels"], stderr=subprocess.STDOUT, timeout=2
        ).decode()
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return len(lines) > 1
    except Exception:
        return False


def _detect_best_encoder() -> str:
    """Return the best hardware encoder ``ffmpeg`` supports.

    The detection checks for common GPU encoder names and returns the
    corresponding ``-hwaccel`` flag. ``"false"`` is returned when no supported
    encoder is found or ``ffmpeg`` is missing.
    """

    try:
        encoders = subprocess.check_output(
            [FFMPEG_PATH, "-encoders", "-hide_banner"],
            stderr=subprocess.STDOUT,
            timeout=2,
        ).decode()
    except Exception:
        return "false"

    mappings = [
        ("h264_nvenc", "cuda"),
        ("h264_vaapi", "vaapi"),
        ("h264_qsv", "qsv"),
        ("h264_v4l2m2m", "v4l2m2m"),
    ]
    for codec, accel in mappings:
        if re.search(codec, encoders):
            return accel
    return "false"


# Enable GPU acceleration by default. "auto" lets ffmpeg pick the best
# available method and falls back to software when no GPU is present.
_hwaccel_cfg = get_setting("FFMPEG_HWACCEL", "auto")
if _hwaccel_cfg.lower() == "auto":
    FFMPEG_HWACCEL = _detect_best_encoder()
else:
    FFMPEG_HWACCEL = _hwaccel_cfg

# Number of threads FFmpeg should use when encoding/decoding
_ffmpeg_threads_cfg = int(
    get_setting("FFMPEG_THREADS", max(1, (os.cpu_count() or 1) // 2))
)
FFMPEG_THREADS = (
    max(1, min(_ffmpeg_threads_cfg, 2)) if LOW_CPU_MODE else _ffmpeg_threads_cfg
)

# CLIP model used for object filtering in scheduling
CLIP_MODEL_NAME = get_setting(
    "CLIP_MODEL_NAME",
    "openai/clip-vit-base-patch32",
)

# Path to ONNX model used for object filtering
CLIP_MODEL_PATH = get_setting(
    "CLIP_MODEL_PATH",
    "models/clip-vit-b-32.onnx",
)


# New settings for capture_frame_from_stream function
NUM_FRAMES = int(get_setting("NUM_FRAMES", 3))
CAPTURE_TIMEOUT = int(get_setting("CAPTURE_TIMEOUT", 30))
PROBE_SIZE_DEFAULT = get_setting("PROBE_SIZE_DEFAULT", "5M")
PROBE_SIZE_RTSP = get_setting("PROBE_SIZE_RTSP", "10M")
PROBE_SIZE_OTHER = get_setting("PROBE_SIZE_OTHER", "20M")

# Analysis duration values for ffmpeg's stream probing. They default to the
# corresponding probe size values but can be overridden independently if
# needed.
ANALYZE_DURATION_DEFAULT = get_setting("ANALYZE_DURATION_DEFAULT", PROBE_SIZE_DEFAULT)
ANALYZE_DURATION_RTSP = get_setting("ANALYZE_DURATION_RTSP", PROBE_SIZE_RTSP)
ANALYZE_DURATION_OTHER = get_setting("ANALYZE_DURATION_OTHER", PROBE_SIZE_OTHER)

# Frame rate used when `generate_live_stream` falls back to
# still image capture. Increase to get smoother previews if
# your hardware can handle the extra load.
_live_fallback_fps_cfg = int(get_setting("LIVE_FALLBACK_FPS", 1))
LIVE_FALLBACK_FPS = (
    max(1, min(_live_fallback_fps_cfg, 1)) if LOW_CPU_MODE else _live_fallback_fps_cfg
)

# Live RTSP playback: optionally transcode to a smaller H.264 stream so browsers
# start quickly (and so 4K camera feeds don't overwhelm the client/network).
LIVE_TRANSCODE_RTSP = get_setting("LIVE_TRANSCODE_RTSP", "True") == "True"
_live_rtsp_width_cfg = int(get_setting("LIVE_RTSP_WIDTH", 1280))
LIVE_RTSP_WIDTH = max(320, min(_live_rtsp_width_cfg, 3840))
_live_rtsp_fps_cfg = int(get_setting("LIVE_RTSP_FPS", 10))
LIVE_RTSP_FPS = max(1, min(_live_rtsp_fps_cfg, 30))

# In low CPU mode, be more conservative with live playback.
if LOW_CPU_MODE:
    LIVE_RTSP_WIDTH = min(LIVE_RTSP_WIDTH, 640)
    LIVE_RTSP_FPS = min(LIVE_RTSP_FPS, 5)

# Socket / IO timeouts (microseconds) for live stream startup/read.
LIVE_RTSP_RW_TIMEOUT_US = int(get_setting("LIVE_RTSP_RW_TIMEOUT_US", 15000000))
LIVE_RTSP_SOCKET_TIMEOUT_US = int(get_setting("LIVE_RTSP_SOCKET_TIMEOUT_US", 15000000))

# Skip expensive preflight checks when a given URL/host was recently proven
# healthy. This makes camera flipping feel NVR-fast while still keeping
# circuit-breakers for degraded networks.
LIVE_PREFLIGHT_SKIP_OK_SECONDS = int(get_setting("LIVE_PREFLIGHT_SKIP_OK_SECONDS", 20))

# Best-effort in-process concurrency limits per host for live playback.
# Note: multiple workers won't coordinate, so these are primarily to prevent
# stampedes within a single worker.
LIVE_HOST_MAX_STREAMS = int(get_setting("LIVE_HOST_MAX_STREAMS", 2))

# Stop restarting live streams endlessly when ffmpeg repeatedly fails. If the
# live view fails this many times in a row without producing any output,
# ``generate_live_stream`` gives up and closes the connection so resources are
# not wasted.
LIVE_MAX_FAILURES = int(get_setting("LIVE_MAX_FAILURES", 10))

# Maximum seconds to wait between live stream restarts when ffmpeg exits
# without producing any output. The delay increases exponentially on each
# consecutive failure up to this limit.
LIVE_MAX_RETRY_DELAY = int(get_setting("LIVE_MAX_RETRY_DELAY", 30))

# Duration of the caption chyron scroll in seconds. Set to 0 to disable
# the chyron entirely. When enabled, the same value controls how long
# the banner remains visible after a caption arrives.
CHYRON_SPEED = int(get_setting("CHYRON_SPEED", 0))

# Length in seconds returned by the `/clip/<template>` endpoint.
DEFAULT_CLIP_DURATION = int(get_setting("DEFAULT_CLIP_DURATION", 120))

# Maximum age in minutes before temporary ``clip.mp4`` files are purged.

# Minutes over which initial crawler jobs are staggered at startup to
# avoid CPU spikes when many templates are scheduled.
CRAWLER_STARTUP_SPREAD = int(get_setting("CRAWLER_STARTUP_SPREAD", 10))

MAX_CLIP_AGE_MINUTES = int(get_setting("MAX_CLIP_AGE_MINUTES", 5))

# Skip clip pre-rendering when the number of cameras exceeds this limit.
# Set to 0 to always refresh clips regardless of count.
CLIP_REFRESH_MAX_CAMERAS = int(get_setting("CLIP_REFRESH_MAX_CAMERAS", 10))

# Whether the System Performance icon in the navigation bar should remain
# visible even when the application reports healthy status. When set to
# ``False`` the icon hides itself if all metrics look nominal to reduce
# clutter. Set ``True`` to keep it visible at all times.
HEALTH_STATUS_ALWAYS_VISIBLE = (
    get_setting("HEALTH_STATUS_ALWAYS_VISIBLE", "False") == "True"
)

# Watchdog configuration values. These control how aggressively the
# watchdog restarts the application when health checks fail.
WATCHDOG_FAILURE_THRESHOLD = int(get_setting("WATCHDOG_FAILURE_THRESHOLD", 3))
WATCHDOG_RESTART_COOLDOWN = int(get_setting("WATCHDOG_RESTART_COOLDOWN", 900))
WATCHDOG_MAX_FILE_HANDLES = int(get_setting("WATCHDOG_MAX_FILE_HANDLES", 1000))
WATCHDOG_CPU_THRESHOLD = int(get_setting("WATCHDOG_CPU_THRESHOLD", 80))
WATCHDOG_MEMORY_THRESHOLD = int(get_setting("WATCHDOG_MEMORY_THRESHOLD", 80))

# Background discovery runs on a schedule when enabled.  Set this
# to ``True`` to run an hourly scan automatically.
DISCOVERY_AUTOSTART = get_setting("DISCOVERY_AUTOSTART", "False") == "True"

# Email settings
EMAIL_ENABLED = get_setting("EMAIL_ENABLED", "False")
EMAIL_SENDER = get_setting("EMAIL_SENDER", "")
EMAIL_RECIPIENTS = get_setting("EMAIL_RECIPIENTS", "")
EMAIL_SMTP_SERVER = get_setting("EMAIL_SMTP_SERVER", "")
EMAIL_SMTP_PORT = get_setting("EMAIL_SMTP_PORT", "587")
EMAIL_SMTP_TIMEOUT = int(get_setting("EMAIL_SMTP_TIMEOUT", "5"))
EMAIL_USE_TLS = get_setting("EMAIL_USE_TLS", "True")
EMAIL_USERNAME = get_setting("EMAIL_USERNAME", "")
EMAIL_PASSWORD = get_setting("EMAIL_PASSWORD", "")


# SMS/Twilio settings
SMS_ENABLED = get_setting("SMS_ENABLED", "False")
TWILIO_SID = get_setting("TWILIO_SID", "")
TWILIO_TOKEN = get_setting("TWILIO_TOKEN", "")
TWILIO_NUMBER = get_setting("TWILIO_NUMBER", "")
TWILIO_FROM_NUMBER = get_setting("TWILIO_FROM_NUMBER", "")

# Web Push settings
VAPID_PUBLIC_KEY = get_setting("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = get_setting("VAPID_PRIVATE_KEY", "")

# Notification toggles
NOTIFY_ON_MOTION = get_setting("NOTIFY_ON_MOTION", "True") == "True"
NOTIFY_ON_CAPTION = get_setting("NOTIFY_ON_CAPTION", "True") == "True"

# Common Alerting Protocol settings
CAP_ENABLED = get_setting("CAP_ENABLED", "False")
CAP_ENDPOINT = get_setting("CAP_ENDPOINT", "")
CAP_SENDER = get_setting("CAP_SENDER", "")

# MCP settings
MCP_SERVER_COMMAND = get_setting("MCP_SERVER_COMMAND", "")
MCP_SERVER_URL = get_setting("MCP_SERVER_URL", "")

# When ``True`` the ``/robots.txt`` route allows search engine indexing.
# ``False`` (the default) disallows all crawlers.
ALLOW_BOTS = get_setting("ALLOW_BOTS", "False") == "True"

# Branch to auto-update from when new releases are available. "None" disables
# automatic updates. Values other than "Main" or "Staging" revert to "None".
AUTO_UPDATE_BRANCH = get_setting("AUTO_UPDATE_BRANCH", "None")
if AUTO_UPDATE_BRANCH not in {"None", "Main", "Staging"}:
    logging.warning("Invalid AUTO_UPDATE_BRANCH %s", AUTO_UPDATE_BRANCH)
    AUTO_UPDATE_BRANCH = "None"

# Settings that should never be displayed in the UI
SENSITIVE_SETTINGS = [
    "SECRET_KEY",
    "DATABASE_URL",
    "VERSION",
    "GOOGLE_SDM_PROFILES",
    "EUFY_CLOUD_PROFILES",
]
