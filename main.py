#!./env/bin/python3
#  main.py

import logging
import os
import subprocess
import argparse
import random
import time
import signal
import sys
import threading
import atexit
import socket

import app.config as config
from app import create_app
from app import scheduler
from app.utils.scheduling import get_system_metrics, stop_background_tasks

banner = """
          ____  _  _
         / ___|| |(_)_ __ ___  _ __  ___  ___ _ __
        | |  _ | || | '_ ` _ `| '_ `/ __|/ _ ` '__|
        | |_| || || | | | | | | |_) `__ '  __/ |
         `____||_||_|_| |_| |_| .__/|___/`___|_|
                              |_|
"""


def parse_arguments(arg_list=None):
    """
    Parse command-line arguments for the Glimpser application.

    This function sets up the argument parser and defines various command-line options
    for configuring the application, including paths for database, logs, and media files,
    as well as server and logging settings.

    Returns:
        argparse.Namespace: An object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Glimpser %s" % config.VERSION)
    parser.add_argument(
        "--db-path",
        default=config.DATABASE_PATH,
        help="Path to the database file (default: %s)" % config.DATABASE_PATH,
    )
    parser.add_argument(
        "--host",
        default=config.HOST,
        help="Host for the web server (default: %s)" % config.HOST,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.PORT,
        help="Port for the web server (default: %s)" % config.PORT,
    )
    parser.add_argument(
        "--log-path",
        default=config.LOGGING_PATH,
        help="Path to the log file (default: %s)" % config.LOGGING_PATH,
    )
    parser.add_argument(
        "--log-level",
        default=config.LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    parser.add_argument(
        "--console-log",
        action="store_true",
        help="Enable logging to the console",
        default=False,
    )
    parser.add_argument(
        "--debug", action="store_true", default=config.DEBUG, help="Enable debug mode"
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Disable the background scheduler",
        default=False,
    )
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Disable the watchdog thread",
        default=False,
    )
    parser.add_argument(
        "--no-crawlers",
        action="store_true",
        help="Skip scheduling crawler jobs",
        default=False,
    )
    parser.add_argument(
        "--screenshot-dir",
        default=config.SCREENSHOT_DIRECTORY,
        help="Directory for storing screenshots",
    )
    parser.add_argument(
        "--video-dir",
        default=config.VIDEO_DIRECTORY,
        help="Directory for storing video files",
    )
    parser.add_argument(
        "--summaries-dir",
        default=config.SUMMARIES_DIRECTORY,
        help="Directory for storing summaries",
    )
    return parser.parse_args(arg_list)


def setup_config(args=None):
    """
    Set up the application configuration based on command-line arguments or default values.

    Args:
        args (argparse.Namespace, optional): Parsed command-line arguments. Defaults to None.

    If args is None, the function assumes the application is running via Gunicorn and uses default config values.
    """
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
    """
    Configure the logging system for the application.

    Args:
        args (argparse.Namespace, optional): Parsed command-line arguments. Defaults to None.

    This function sets up file logging and optionally console logging based on the provided arguments.
    """
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, args.log_level if args else config.LOG_LEVEL))

    # Ensure log directory exists
    os.makedirs(os.path.dirname(config.LOGGING_PATH), exist_ok=True)

    # Set up file logging
    file_handler = logging.FileHandler(config.LOGGING_PATH)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Set up console logging if requested
    if args and args.console_log:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


def ensure_directories():
    """
    Create necessary directories for the application if they don't exist.

    This function creates directories for the database, logs, screenshots, videos, and summaries.
    """
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(config.LOGGING_PATH), exist_ok=True)
    os.makedirs(config.SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(config.VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(config.SUMMARIES_DIRECTORY, exist_ok=True)


def generate_credentials_if_needed():
    """
    Generate credentials if the database file doesn't exist.

    This function checks if the database file exists, and if not, it calls the generate_credentials function
    to create new credentials.
    """
    if not os.path.exists(config.DATABASE_PATH):
        from generate_credentials import generate_credentials

        generate_credentials(args=None)


def create_application(args=None):
    """
    Create and configure the Flask application.

    This function sets up the entire application, including parsing arguments, setting up configuration and logging,
    ensuring necessary directories exist, and generating credentials if needed.

    Returns:
        Flask: The configured Flask application instance.
    """
    if args is None:
        if __name__ == "__main__":
            args = parse_arguments()
        # When running via Gunicorn or tests without CLI
        else:
            args = None

    if args:
        setup_config(args)
        setup_logging(args)
    else:
        setup_config()
        setup_logging()

    ensure_directories()
    generate_credentials_if_needed()

    schedule = not getattr(args, "no_scheduler", False)
    enable_watchdog = not getattr(args, "no_watchdog", False)
    crawlers = not getattr(args, "no_crawlers", False)

    return create_app(
        enable_watchdog=enable_watchdog, schedule=schedule, crawlers=crawlers
    )


def output_shutdown_stats():
    # Get and display system metrics
    metrics = get_system_metrics()
    logging.info("System Metrics at Shutdown:")
    logging.info("CPU Usage: %s%%", metrics["cpu_usage"])
    logging.info("Memory Usage: %s%%", metrics["memory_usage"])
    logging.info("Disk Usage: %s%%", metrics["disk_usage"])
    logging.info("Open Files: %s", metrics["open_files"])
    logging.info("Thread Count: %s", metrics["thread_count"])
    logging.info("Uptime: %s", metrics["uptime"])
    logging.info("FFmpeg Version: %s", metrics["ffmpeg_version"])
    logging.info("Machine HW Accel: %s", metrics["machine_hwaccel"])
    logging.info("FFmpeg HW Accel: %s", metrics["ffmpeg_hwaccel"])
    logging.info("HW Accel Enabled: %s", metrics["hwaccel_enabled"])
    logging.info("Thank you for running Glimpser. Goodbye!")


class CleanupManager:
    """Manage application shutdown state."""

    def __init__(self):
        self.display_note = True
        self._cleanup_called = False
        self._lock = threading.Lock()

    def cleanup(self):
        """Release resources and stop running threads."""
        with self._lock:
            if self._cleanup_called:
                return
            self._cleanup_called = True

        try:
            scheduler.shutdown(wait=True)
        except Exception as e:
            logging.error("Error shutting down scheduler: %s", e)

        stop_background_tasks()

        time.sleep(0.01)
        for thread in threading.enumerate():
            if thread != threading.current_thread():
                self.display_note = False
                try:
                    thread.join(timeout=0.01)
                    if thread.is_alive():
                        logging.warning(
                            "Thread %s is still alive after join", thread.name
                        )
                except Exception as e:
                    logging.error("Error terminating thread %s: %s", thread.name, e)

        output_shutdown_stats()


shutdown_manager = CleanupManager()


def cleanup_resources():
    """Backward-compatible cleanup wrapper."""
    shutdown_manager.cleanup()


def graceful_shutdown(signum, frame):
    """Handle termination signals by cleaning up and exiting."""
    logging.info("Received signal %s. Shutting down...", signum)
    cleanup_resources()
    time.sleep(0.01)
    sys.exit(0)


def clear_console():
    """Clear the terminal in a platform agnostic way."""
    command = ["cls"] if os.name == "nt" else ["clear"]
    subprocess.run(command, check=False)


def clear_console_cli():
    """Entry point for the ``glimpser-clear`` command."""
    clear_console()


STARTUP_TIPS = [
    "Set SESSION_COOKIE_SECURE=False when running without HTTPS.",
    "Use --console-log to mirror logs to your terminal.",
    "See docs/startup_tips.md for more tips.",
]


def display_startup_tips():
    """Log common setup reminders."""
    border = "-" * 60
    logging.info(border)
    logging.info("Startup Tips")
    logging.info(border)
    for tip in STARTUP_TIPS:
        logging.info("* %s", tip)
    logging.info(border)
    if config.SESSION_COOKIE_SECURE:
        logging.warning(
            "SESSION_COOKIE_SECURE is enabled; browsers only send the login cookie over HTTPS."
        )


def is_port_in_use(port):
    # Skip the check if running in Docker
    if os.environ.get("IN_DOCKER"):
        return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def main(argv=None):
    """Entry point for the ``glimpser`` command."""
    # Clear the console before starting
    clear_console()

    logging.info(banner)
    display_startup_tips()

    atexit.register(cleanup_resources)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    logging.info("Initializing...")
    args = parse_arguments(argv)
    app = create_application(args)

    if is_port_in_use(config.PORT) and config.DEBUG_MODE is False:
        logging.error(
            "Error: Port %s is already in use. Please choose a different port.",
            config.PORT,
        )
        sys.exit(1)

    try:
        logging.info(
            "Starting web interface at http://%s:%s",
            config.HOST,
            config.PORT,
        )
        app.run(
            host=config.HOST, port=config.PORT, debug=config.DEBUG_MODE, threaded=True
        )
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received. Cleaning up...")
        cleanup_resources()
    except Exception as e:
        logging.error("An error occurred while running the application: %s", e)
    finally:
        cleanup_resources()
        logging.info("Glimpser shut down.")


if __name__ == "__main__":
    main()
