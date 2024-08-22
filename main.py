import logging
import os
import argparse
import app.config as config
from app import create_app

def parse_arguments():
    parser = argparse.ArgumentParser(description="Glimpser %s" % config.VERSION)
    parser.add_argument("--db-path", default=config.DATABASE_PATH,
            help="Path to the database file (default: %s)" % config.DATABASE_PATH)
    parser.add_argument("--host", default=config.HOST, help="Host for the web server (default: %s)" % config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT, help="Port for the web server (default: %s)" % config.PORT)
    parser.add_argument("--log-path", default=config.LOGGING_PATH,
            help="Path to the log file (default: %s)" % config.LOGGING_PATH)
    parser.add_argument("--log-level", default=config.LOG_LEVEL, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Logging level")
    parser.add_argument("--console-log", action="store_true", help="Enable logging to the console", default=False)
    parser.add_argument("--debug", action="store_true", default=config.DEBUG,
                        help="Enable debug mode")
    parser.add_argument("--screenshot-dir", default=config.SCREENSHOT_DIRECTORY,
                        help="Directory for storing screenshots")
    parser.add_argument("--video-dir", default=config.VIDEO_DIRECTORY,
                        help="Directory for storing video files")
    parser.add_argument("--summaries-dir", default=config.SUMMARIES_DIRECTORY,
                        help="Directory for storing summaries")
    return parser.parse_args()

def setup_config(args=None):
    if args is None:
        # Use default config values when running via Gunicorn
        return

    # Update variables based on command-line arguments
    config.DATABASE_PATH = args.db_path
    config.HOST = args.host
    config.PORT = args.port
    config.LOGGING_PATH = args.log_path
    config.DEBUG_MODE = args.debug
    config.SCREENSHOT_DIRECTORY = args.screenshot_dir
    config.VIDEO_DIRECTORY = args.video_dir
    config.SUMMARIES_DIRECTORY = args.summaries_dir

def setup_logging(args=None):
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, args.log_level if args else config.LOG_LEVEL))

    # Ensure log directory exists
    os.makedirs(os.path.dirname(config.LOGGING_PATH), exist_ok=True)

    file_handler = logging.FileHandler(config.LOGGING_PATH)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if args and args.console_log:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

def ensure_directories():
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(config.LOGGING_PATH), exist_ok=True)
    os.makedirs(config.SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(config.VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(config.SUMMARIES_DIRECTORY, exist_ok=True)

def generate_credentials_if_needed():
    if not os.path.exists(config.DATABASE_PATH):
        from generate_credentials import generate_credentials
        generate_credentials()

def create_application():
    if __name__ == "__main__":
        args = parse_arguments()
        setup_config(args)
        setup_logging(args)
    else:
        # Running via Gunicorn
        setup_config()
        setup_logging()

    ensure_directories()
    generate_credentials_if_needed()

    return create_app()

app = create_application()

if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG_MODE, threaded=True)
