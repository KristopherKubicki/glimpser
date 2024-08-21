# config.py

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# TODO: also consider argparse...
DATABASE_PATH = os.getenv("GLIMPSER_DATABASE_PATH", "data/glimpser.db")
LOGGING_PATH = os.getenv("GLIMPSER_LOGGING_PATH", "logs/glimpser.log")

# todo.. make sure this is not duplicate loading...
engine = create_engine(f"sqlite:///{DATABASE_PATH}")
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)  # settings only tthread


def get_setting(name, default=None):

    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT value FROM settings WHERE name = '%s'" % name)
        ).fetchone()
        return result[0] if result else default
    except Exception as e:
        if 'no such table' in str(e):
            # this is ok if its the first time only... 
            print("warning! table does not exist")
            pass
        else:
            print("warning! initialization error", e)
    finally:
        session.close()

    return default


SCHEDULER_API_ENABLED = True

# be careful when mounting network devices
SCREENSHOT_DIRECTORY = "data/screenshots/"
VIDEO_DIRECTORY = "data/video/"
SUMMARIES_DIRECTORY = "data/summaries/"

# Load settings from the database
UA = get_setting(
    "UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
)
LANG = get_setting("LANG", "en-US")
VERSION = float(get_setting("VERSION", 0.1))
NAME = get_setting("NAME", "glimpser")
HOST = get_setting("HOST", "0.0.0.0")
PORT = int(get_setting("PORT", 8082))
DEBUG = get_setting("DEBUG", "True") == "True"
MAX_WORKERS = get_setting("MAX_WORKERS", 8)

# Thresholds
MAX_RAW_DATA_SIZE = int(get_setting("MAX_RAW_DATA_SIZE", 500 * 1024 * 1024))  # 500 MB
MAX_IMAGE_RETENTION_AGE = int(get_setting("MAX_IMAGE_RETENTION_AGE", 8))
MAX_VIDEO_RETENTION_AGE = int(get_setting("MAX_VIDEO_RETENTION_AGE", 365))
MAX_COMPRESSED_VIDEO_AGE = int(get_setting("MAX_COMPRESSED_VIDEO_AGE", 7))  # days
MAX_IN_PROCESS_VIDEO_SIZE = int(
    get_setting("MAX_IN_PROCESS_VIDEO_SIZE", 100 * 1024 * 1024)
)  # 100 MB

LOG_LEVEL = get_setting("LOG_LEVEL","DEBUG")

# Load settings from the database
SECRET_KEY = get_setting("SECRET_KEY", "default_secret_key")
USER_NAME = get_setting("USER_NAME", "admin")
USER_PASSWORD_HASH = get_setting("USER_PASSWORD_HASH", "")
API_KEY = get_setting("API_KEY", "")
CHATGPT_KEY = get_setting("CHATGPT_KEY", "")

LLM_MODEL_VERSION = get_setting("LLM_MODEL_VERSION", "gpt-4o-mini")

# note that $datetime is a special keyword that will be replaced with the datetime in iso Z format
LLM_SUMMARY_PROMPT = get_setting(
    "LLM_SUMMARY_PROMPT",
    "Summarize the following logs into a concise, technical transcript. Focus on providing clear, actionable insights and key takeaways. Keep the summary brief and organized, with one line per segment, separated by newlines. Start with a brief overview, including any major events or trends. Prioritize clarity and relevance, ensuring the summary is easy to understand and useful for decision-making. Avoid repetition unless necessary. Conclude with a brief summary or closing note. The time is $datetime.",
)

LLM_CAPTION_PROMPT = get_setting(
    "LLM_CAPTION_PROMPT",
    "Write a concise caption that highlights the most significant or unique aspect of this image in 10 words or less. Avoid general descriptions, and focus on noteworthy details or anomalies. Then, provide a brief, more detailed description in a couple of sentences. The time is $datetime UTC.",
)

# experimental
# TWILIO_SID = get_setting("TWILIO_SID","")
# TWILIO_TOKEN = get_setting("TWILIO_TOKEN","")
# TWILIO_NUMBER = get_setting("TWILIO_NUMBER","")
