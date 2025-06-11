#!./env/bin/python3
#  main.py

import argparse
import atexit
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time

import app.config as config
from app import create_app, scheduler
from app.utils.cli import build_argument_parser, cli_help_text
from app.utils.scheduling import get_system_metrics, stop_background_tasks

banner = f"""\033[96m
          ____  _  _
         / ___|| |(_)_ __ ___  _ __  ___  ___ _ __
        | |  _ | || | '_ ` _ `| '_ `/ __|/ _ ` '__|
        | |_| || || | | | | | | |_) `__ '  __/ |
         `____||_||_|_| |_| |_| .__/|___/`___|_| v{config.VERSION}
                              |_|
\033[0m"""


def parse_arguments(arg_list=None):
    """Return parsed command-line arguments."""
    parser = build_argument_parser()
    return parser.parse_args(arg_list)


def get_cli_help() -> str:
    """Return the formatted ``--help`` text."""
    return cli_help_text()


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
    if config.ENFORCE_DOMAIN_IN_HOST and "." not in config.HOST:
        raise ValueError("HOST must include a domain when ENFORCE_DOMAIN_IN_HOST is enabled")
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

    if config.ENFORCE_DOMAIN_IN_HOST and "." not in config.HOST:
        raise ValueError("HOST must include a domain when ENFORCE_DOMAIN_IN_HOST is enabled")

    ensure_directories()
    generate_credentials_if_needed()

    schedule = not getattr(args, "no_scheduler", False)
    enable_watchdog = not getattr(args, "no_watchdog", False)
    crawlers = not getattr(args, "no_crawlers", False)
    log_cache = not getattr(args, "no_log_cache", False)

    return create_app(
        enable_watchdog=enable_watchdog,
        schedule=schedule,
        crawlers=crawlers,
        log_cache=log_cache,
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
    logging.info(
        "FFmpeg Version: %s (%s)",
        metrics["ffmpeg_version"],
        metrics["ffmpeg_path"],
    )
    logging.info("Machine HW Accel: %s", metrics["machine_hwaccel"])
    logging.info("FFmpeg HW Accel: %s", metrics["ffmpeg_hwaccel"])
    logging.info("HW Accel Enabled: %s", metrics["hwaccel_enabled"])
    logging.info("GPU Support: %s", metrics["gpu_support"])
    logging.info("FFmpeg GPU Enabled: %s", metrics["ffmpeg_gpu_enabled"])
    logging.info("Danger Mode: %s", metrics["danger_mode"])
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
                        logging.warning("Thread %s is still alive after join", thread.name)
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
    # Warn when the server binds to a loopback address. Remote
    # clients cannot reach 127.x or localhost hosts.
    if config.HOST.startswith("127.") or config.HOST in {"localhost", "::1"}:
        logging.warning(
            "HOST %s is only reachable locally; remote clients may not connect.",
            config.HOST,
        )
    if config.SESSION_COOKIE_SECURE:
        logging.warning("SESSION_COOKIE_SECURE is enabled; browsers only send the login cookie over HTTPS.")


def _format_table(rows, headers):
    col_widths = [max(len(str(item)) for item in column) for column in zip(headers, *rows)]
    header = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    separator = "-+-".join("-" * w for w in col_widths)
    lines = [header, separator]
    for row in rows:
        lines.append(" | ".join(str(item).ljust(w) for item, w in zip(row, col_widths)))
    return "\n".join(lines)


def display_startup_info(args=None):
    """Log configuration and system metrics in table form."""
    border = "-" * 60
    logging.info(border)
    logging.info("Startup Configuration")
    logging.info(border)
    # Assemble a detailed table of configuration values. Showing paths and
    # flags together makes it easier to confirm everything is wired up
    # correctly when Glimpser launches.
    config_table = [
        ["Version", config.VERSION],
        ["Host", config.HOST],
        ["Port", config.PORT],
        ["Debug Mode", config.DEBUG_MODE],
        ["Log Level", config.LOG_LEVEL],
        ["Database", config.DATABASE_PATH],
        ["Log File", config.LOGGING_PATH],
        ["Screenshots", config.SCREENSHOT_DIRECTORY],
        ["Videos", config.VIDEO_DIRECTORY],
        ["Summaries", config.SUMMARIES_DIRECTORY],
        [
            "Scheduler Enabled",
            "No" if getattr(args, "no_scheduler", False) else "Yes",
        ],
        [
            "Watchdog Enabled",
            "No" if getattr(args, "no_watchdog", False) else "Yes",
        ],
        [
            "Crawlers Enabled",
            "No" if getattr(args, "no_crawlers", False) else "Yes",
        ],
    ]
    logging.info("\n" + _format_table(config_table, ["Option", "Value"]))

    metrics = get_system_metrics()
    logging.info(border)
    logging.info("System Metrics")
    logging.info(border)
    # Capture richer runtime details so administrators have a snapshot of the
    # environment before connecting to the web UI.
    metrics_table = [
        ["CPU Usage", f"{metrics['cpu_usage']}%"],
        ["Memory Usage", f"{metrics['memory_usage']}%"],
        ["Disk Usage", f"{metrics['disk_usage']}%"],
        ["Open Files", metrics["open_files"]],
        ["Thread Count", metrics["thread_count"]],
        ["Uptime", metrics["uptime"]],
        ["FFmpeg", metrics["ffmpeg_version"]],
        ["HW Accel", "Yes" if metrics["hwaccel_enabled"] else "No"],
        ["GPU Support", "Yes" if metrics["gpu_support"] else "No"],
        ["Danger Mode", "Yes" if metrics["danger_mode"] else "No"],
    ]
    logging.info("\n" + _format_table(metrics_table, ["Metric", "Value"]))
    logging.info(border)


def is_port_in_use(port):
    # Skip the check if running in Docker
    if os.environ.get("IN_DOCKER"):
        return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def get_port_usage(port: int) -> str:
    """Return any process details using ``port`` or an empty string."""
    commands = [["lsof", "-i", f":{port}"], ["fuser", "-n", "tcp", str(port)]]
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                return output
        except FileNotFoundError:
            continue
    return ""


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
    display_startup_info(args)

    if is_port_in_use(config.PORT) and config.DEBUG_MODE is False:
        logging.error(
            "Error: Port %s is already in use. Please choose a different port.",
            config.PORT,
        )
        usage = get_port_usage(config.PORT)
        if usage:
            logging.error("Processes using port %s:\n%s", config.PORT, usage)
        else:
            logging.error(
                "Could not determine which process is using port %s.",
                config.PORT,
            )
        sys.exit(1)

    try:
        logging.info(
            "Starting web interface at http://%s:%s",
            config.HOST,
            config.PORT,
        )
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG_MODE, threaded=True)
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
