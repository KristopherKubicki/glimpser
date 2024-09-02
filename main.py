#!env/bin/python3
#  main.py

import logging
import os
import argparse
import signal
import app.config as config
from app import create_app

banner = """
  ____  _  _
 / ___|| |(_)_ __ ___  _ __  ___  ___ _ __
| |  _ | || | '_ ` _ `| '_ `/ __|/ _ ` '__|
| |_| || || | | | | | | |_) `__ '  __/ |
 `____||_||_|_| |_| |_| .__/|___/`___|_|
                      |_|
"""

def parse_arguments():
    """
    Parse command-line arguments for the Glimpser application.

    This function sets up the argument parser and defines various command-line options
    for configuring the application, including paths for database, logs, and media files,
    as well as server and logging settings.

    Returns:
        argparse.Namespace: An object containing the parsed arguments.
    """
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

def create_application():
    """
    Create and configure the Flask application.

    This function sets up the entire application, including parsing arguments, setting up configuration and logging,
    ensuring necessary directories exist, and generating credentials if needed.

    Returns:
        Flask: The configured Flask application instance.
    """
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


import signal, sys, threading 
# Define your graceful_shutdown function
def graceful_shutdown(signum, frame):

    if threading.current_thread() is threading.main_thread():
        print("\nReceived shutdown signal. Shutting down gracefully...")

    from app.utils.scheduling import get_system_metrics
    def output_shutdown_stats():
        # Get and display system metrics
        metrics = get_system_metrics()
        print("\nSystem Metrics at Shutdown:")
        print(f"CPU Usage: {metrics['cpu_usage']}%")
        print(f"Memory Usage: {metrics['memory_usage']}%")
        print(f"Disk Usage: {metrics['disk_usage']}%")
        print(f"Open Files: {metrics['open_files']}")
        print(f"Thread Count: {metrics['thread_count']}")
        print(f"Uptime: {metrics['uptime']}")
        print("\nGlimpser application has been shut down gracefully. All threads terminated. Goodbye!")

    from app import scheduler 
    # Shutdown the scheduler
    try:
        scheduler.shutdown(wait=False)
    except Exception as e:
        print(f"Error shutting down scheduler: {e}")

    # Terminate all non-daemon threads
    for thread in threading.enumerate():
        if thread != threading.current_thread() and not thread.daemon:
            try:
                thread.join(timeout=1)
            except Exception as e:
                print(f"Error terminating thread {thread.name}: {e}")

    # Add any other cleanup tasks here (e.g., closing database connections)

    if threading.current_thread() is threading.main_thread():
        output_shutdown_stats()
        sys.exit(0)

if __name__ == "__main__":
    # Create the Flask application
    app = create_application()

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    try:
        # Run the application if this script is executed directly
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG_MODE, threaded=True)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received. Exiting...")
    finally:
        print("Glimpser shut down.")
