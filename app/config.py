# config.py

import os
import json
import secrets
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Environment variables with secure defaults
DATABASE_PATH = os.getenv("GLIMPSER_DATABASE_PATH", "data/glimpser.db")
LOGGING_PATH = os.getenv("GLIMPSER_LOGGING_PATH", "logs/glimpser.log")
BACKUP_PATH = os.getenv("GLIMPSER_BACKUP_PATH", "data/config_backup.json")

# Database connection with pooling and timeout
engine = create_engine(f"sqlite:///{DATABASE_PATH}", pool_size=5, max_overflow=10, pool_timeout=30)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_setting(name, default=None):
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT value FROM settings WHERE name = :name"),
            {"name": name}
        ).fetchone()
        return result[0] if result else default
    except Exception as e:
        if 'no such table' in str(e):
            print("Warning: Settings table does not exist")
        else:
            print(f"Warning: Initialization error - {e}")
    finally:
        session.close()
    return default

def backup_config():
    session = SessionLocal()
    try:
        settings = session.execute(text("SELECT name, value FROM settings")).fetchall()
        config_dict = {name: value for name, value in settings}
        with open(BACKUP_PATH, 'w') as f:
            json.dump(config_dict, f)
    finally:
        session.close()

def restore_config():
    if os.path.exists(BACKUP_PATH):
        with open(BACKUP_PATH, 'r') as f:
            config_dict = json.load(f)
        
        session = SessionLocal()
        try:
            for name, value in config_dict.items():
                session.execute(
                    text("INSERT OR REPLACE INTO settings (name, value) VALUES (:name, :value)"),
                    {"name": name, "value": value}
                )
            session.commit()
        finally:
            session.close()

SCHEDULER_API_ENABLED = False  # Disable scheduler API for security

# Secure file paths
SCREENSHOT_DIRECTORY = os.path.abspath("data/screenshots/")
VIDEO_DIRECTORY = os.path.abspath("data/video/")
SUMMARIES_DIRECTORY = os.path.abspath("data/summaries/")

# Load settings from the database with secure defaults
UA = get_setting("UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")
LANG = get_setting("LANG", "en-US")
VERSION = float(get_setting("VERSION", 0.1))
NAME = get_setting("NAME", "glimpser")
HOST = get_setting("HOST", "127.0.0.1")  # Changed to localhost for security
PORT = int(get_setting("PORT", 8082))
DEBUG = False  # Disable debug mode in production
MAX_WORKERS = min(int(get_setting("MAX_WORKERS", 8)), 16)  # Limit max workers

# Thresholds with more conservative defaults
MAX_RAW_DATA_SIZE = min(int(get_setting("MAX_RAW_DATA_SIZE", 100 * 1024 * 1024)), 500 * 1024 * 1024)  # 100 MB default, max 500 MB
MAX_IMAGE_RETENTION_AGE = min(int(get_setting("MAX_IMAGE_RETENTION_AGE", 7)), 30)  # 7 days default, max 30 days
MAX_VIDEO_RETENTION_AGE = min(int(get_setting("MAX_VIDEO_RETENTION_AGE", 30)), 365)  # 30 days default, max 1 year
MAX_COMPRESSED_VIDEO_AGE = min(int(get_setting("MAX_COMPRESSED_VIDEO_AGE", 7)), 30)  # 7 days default, max 30 days
MAX_IN_PROCESS_VIDEO_SIZE = min(int(get_setting("MAX_IN_PROCESS_VIDEO_SIZE", 50 * 1024 * 1024)), 100 * 1024 * 1024)  # 50 MB default, max 100 MB

LOG_LEVEL = get_setting("LOG_LEVEL", "INFO")

# Security settings
SECRET_KEY = get_setting("SECRET_KEY", secrets.token_hex(32))  # Generate a secure secret key if not set
USER_NAME = get_setting("USER_NAME", "admin")
USER_PASSWORD_HASH = get_setting("USER_PASSWORD_HASH", "")  # Ensure this is set securely
API_KEY = get_setting("API_KEY", secrets.token_urlsafe(32))  # Generate a secure API key if not set
CHATGPT_KEY = get_setting("CHATGPT_KEY", "")

LLM_MODEL_VERSION = get_setting("LLM_MODEL_VERSION", "gpt-4o-mini")

# Prompts (unchanged)
LLM_SUMMARY_PROMPT = get_setting(
    "LLM_SUMMARY_PROMPT",
    "Summarize the following logs into a concise, technical transcript. Focus on providing clear, actionable insights and key takeaways. Keep the summary brief and organized, with one line per segment, separated by newlines. Start with a brief overview, including any major events or trends. Prioritize clarity and relevance, ensuring the summary is easy to understand and useful for decision-making. Avoid repetition unless necessary. Conclude with a brief summary or closing note. The time is $datetime.",
)

LLM_CAPTION_PROMPT = get_setting(
    "LLM_CAPTION_PROMPT",
    "Write a concise caption that highlights the most significant or unique aspect of this image in 10 words or less. Avoid general descriptions, and focus on noteworthy details or anomalies. Then, provide a brief, more detailed description in a couple of sentences. The time is $datetime UTC.",
)

# FFMPEG path setting
FFMPEG_PATH = get_setting("FFMPEG_PATH", "ffmpeg")

# Session configuration
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Content Security Policy
CSP_POLICY = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; form-action 'self';"

# CORS settings
CORS_ORIGINS = ['https://example.com']  # Add allowed origins

# Rate limiting
RATELIMIT_DEFAULT = "100/hour"
RATELIMIT_STORAGE_URL = "memory://"

# Experimental settings (commented out for now)
# TWILIO_SID = get_setting("TWILIO_SID","")
# TWILIO_TOKEN = get_setting("TWILIO_TOKEN","")
# TWILIO_NUMBER = get_setting("TWILIO_NUMBER","")
