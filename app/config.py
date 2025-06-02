# config.py

import os
import json
import logging
import argparse
from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv, find_dotenv

# Load variables from a `.env` file if present
load_dotenv(find_dotenv())

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# Parse command line arguments when executed directly
def _parse_cli_args():
    parser = argparse.ArgumentParser(description="Glimpser configuration")
    parser.add_argument("--db-path", help="Path to the SQLite database file")
    parser.add_argument("--log-path", help="Path to the log file")
    parser.add_argument(
        "--backup-path", help="Path to the configuration backup JSON file"
    )
    return parser.parse_args()


_cli_args = _parse_cli_args() if __name__ == "__main__" else None

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
BACKUP_PATH = (
    _cli_args.backup_path
    if _cli_args and _cli_args.backup_path
    else os.getenv("GLIMPSER_BACKUP_PATH", "data/config_backup.json")
)

# todo.. make sure this is not duplicate loading...
engine = create_engine(f"sqlite:///{DATABASE_PATH}")
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)  # settings only thread


def get_setting(name, default=None):
    """Return a setting from the environment or the database."""
    env_val = os.getenv(name)
    if env_val is not None:
        return env_val

    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT value FROM settings WHERE name = :name"),
            {"name": name},
        ).fetchone()
        return result[0] if result else default
    except Exception as e:
        if "no such table" in str(e):
            # this is ok if its the first time only...
            logging.warning("table does not exist")
            pass
        else:
            logging.warning("initialization error %s", e)
    finally:
        session.close()

    return default


def backup_config() -> bool:
    session = SessionLocal()
    success = True
    try:
        settings = session.execute(text("SELECT name, value FROM settings")).fetchall()
        config_dict = {name: value for name, value in settings}
        with open(BACKUP_PATH, "w") as f:
            json.dump(config_dict, f)
    except Exception:
        success = False
    finally:
        session.close()
    return success


def restore_config():
    if os.path.exists(BACKUP_PATH):
        with open(BACKUP_PATH, "r") as f:
            config_dict = json.load(f)

        session = SessionLocal()
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

    session = SessionLocal()
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
    except Exception as e:
        if "no such table" in str(e):
            logging.warning("table does not exist")
        else:
            logging.warning("initialization error %s", e)
    finally:
        session.close()


SCHEDULER_API_ENABLED = True

# be careful when mounting network devices
SCREENSHOT_DIRECTORY = "data/screenshots/"
VIDEO_DIRECTORY = "data/video/"
SUMMARIES_DIRECTORY = "data/summaries/"

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
    _PKG_VERSION = "0.2.6"
sync_version(_PKG_VERSION)
# Default to the package version if not overridden in the database
VERSION = get_setting("VERSION", _PKG_VERSION)
NAME = get_setting("NAME", "glimpser")
HOST = get_setting("HOST", "0.0.0.0")
PORT = int(get_setting("PORT", 8082))
DEBUG = get_setting("DEBUG", "False") == "True"
# Provide a separate attribute for runtime checks
DEBUG_MODE = DEBUG
MAX_WORKERS = get_setting("MAX_WORKERS", 8)

# Thresholds
MAX_RAW_DATA_SIZE = int(get_setting("MAX_RAW_DATA_SIZE", 500 * 1024 * 1024))  # 500 MB
MAX_IMAGE_RETENTION_AGE = int(get_setting("MAX_IMAGE_RETENTION_AGE", 8))
MAX_VIDEO_RETENTION_AGE = int(get_setting("MAX_VIDEO_RETENTION_AGE", 365))
MAX_COMPRESSED_VIDEO_AGE = int(get_setting("MAX_COMPRESSED_VIDEO_AGE", 7))  # days
MAX_IN_PROCESS_VIDEO_SIZE = int(
    get_setting("MAX_IN_PROCESS_VIDEO_SIZE", 100 * 1024 * 1024)
)  # 100 MB

LOG_LEVEL = get_setting("LOG_LEVEL", "WARN")

# Session security settings
SESSION_COOKIE_SECURE = get_setting("SESSION_COOKIE_SECURE", "True") == "True"
SESSION_COOKIE_HTTPONLY = get_setting("SESSION_COOKIE_HTTPONLY", "True") == "True"
SESSION_TIMEOUT_MINUTES = int(get_setting("SESSION_TIMEOUT_MINUTES", 30))

# Load settings from the database
SECRET_KEY = get_setting("SECRET_KEY", "default_secret_key")
USER_NAME = get_setting("USER_NAME", "admin")
USER_PASSWORD_HASH = get_setting("USER_PASSWORD_HASH", "")
API_KEY = get_setting("API_KEY", "")
SSO_TOKEN = get_setting("SSO_TOKEN", "")
SSO_USERNAME = get_setting("SSO_USERNAME", USER_NAME)
CHATGPT_KEY = get_setting("CHATGPT_KEY", "")  # maybe generalize as LLM_KEY ?

LLM_MODEL_VERSION = get_setting(
    "LLM_MODEL_VERSION", "gpt-4.1-mini"
)  # todo setup allowed models

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
FFMPEG_PATH = get_setting("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = get_setting("FFPROBE_PATH", "ffprobe")
# Enable GPU acceleration if supported (e.g. "auto", "cuda", etc.)
FFMPEG_HWACCEL = get_setting("FFMPEG_HWACCEL", "False")

# CLIP model used for object filtering in scheduling
CLIP_MODEL_NAME = get_setting(
    "CLIP_MODEL_NAME",
    "openai/clip-vit-base-patch32",
)


# New settings for capture_frame_from_stream function
NUM_FRAMES = int(get_setting("NUM_FRAMES", 3))
CAPTURE_TIMEOUT = int(get_setting("CAPTURE_TIMEOUT", 30))
PROBE_SIZE_DEFAULT = get_setting("PROBE_SIZE_DEFAULT", "5M")
PROBE_SIZE_RTSP = get_setting("PROBE_SIZE_RTSP", "10M")
PROBE_SIZE_OTHER = get_setting("PROBE_SIZE_OTHER", "20M")

# Frame rate used when `generate_live_stream` falls back to
# still image capture. Increase to get smoother previews if
# your hardware can handle the extra load.
LIVE_FALLBACK_FPS = int(get_setting("LIVE_FALLBACK_FPS", 1))

# Email settings
EMAIL_ENABLED = get_setting("EMAIL_ENABLED", "False")
EMAIL_SENDER = get_setting("EMAIL_SENDER", "your-email@example.com")
EMAIL_RECIPIENTS = get_setting(
    "EMAIL_RECIPIENTS", "recipient1@example.com,recipient2@example.com"
)
EMAIL_SMTP_SERVER = get_setting("EMAIL_SMTP_SERVER", "smtp.example.com")
EMAIL_SMTP_PORT = get_setting("EMAIL_SMTP_PORT", "587")
EMAIL_USE_TLS = get_setting("EMAIL_USE_TLS", "True")
EMAIL_USERNAME = get_setting("EMAIL_USERNAME", "your-username")
EMAIL_PASSWORD = get_setting("EMAIL_PASSWORD", "")


# SMS/Twilio settings
TWILIO_SID = get_setting("TWILIO_SID", "")
TWILIO_TOKEN = get_setting("TWILIO_TOKEN", "")
TWILIO_NUMBER = get_setting("TWILIO_NUMBER", "")

# Common Alerting Protocol settings
CAP_ENDPOINT = get_setting("CAP_ENDPOINT", "")
CAP_SENDER = get_setting("CAP_SENDER", "glimpser@example.com")

# MCP settings
MCP_SERVER_COMMAND = get_setting("MCP_SERVER_COMMAND", "")
MCP_SERVER_URL = get_setting("MCP_SERVER_URL", "")

# Settings that should never be displayed in the UI
SENSITIVE_SETTINGS = [
    "SECRET_KEY",
    "USER_PASSWORD_HASH",
    "DATABASE_URL",
    "VERSION",
]
