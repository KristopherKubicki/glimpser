# config.py

from auth import SECRET_KEY, USER_NAME, USER_PASSWORD_HASH, API_KEY, CHATGPT_KEY

TEMPLATE_FILE_PATH = 'templates.json'
DATABASE_PATH = 'data/glimpser.db'

SCHEDULER_API_ENABLED = True

# be careful when mounting network devices
SCREENSHOT_DIRECTORY = 'data/screenshots/'
VIDEO_DIRECTORY = 'data/video/' 
SUMMARIES_DIRECTORY = 'data/summaries/' 

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
LANG = "en-US"
VERSION = 0.1
NAME = "glimpser"
HOST = "0.0.0.0"
PORT = 8082
DEBUG = True

# Thresholds
MAX_RAW_DATA_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_IMAGE_RETENTION_AGE = 8

MAX_VIDEO_RETENTION_AGE = 365
MAX_COMPRESSED_VIDEO_AGE = 7  # days - how old is the oldest image in the video?
MAX_IN_PROCESS_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB

class Config(object):
    DEBUG = False
    TESTING = False
    SCREENSHOT_DIR = SCREENSHOT_DIRECTORY
    VIDEO_DIR = VIDEO_DIRECTORY
    SUMMARIES_DIR = SUMMARIES_DIRECTORY

class ProductionConfig(Config):
    pass

class DevelopmentConfig(Config):
    # TODO: read this from the config file?
    DEBUG = True

class TestingConfig(Config):
    # TODO: read this from the config file?
    TESTING = True


