# app/__init__.py

import logging
import os
import threading
import time
import psutil
from datetime import timedelta

from flask import Flask

from app.utils.retention_policy import retention_cleanup
from app.utils.scheduling import (
    schedule_crawlers,
    schedule_summarization,
    scheduler,
    start_log_caching,
)
from app.utils.video_archiver import archive_screenshots, compile_to_teaser
from app.config import backup_config, restore_config
from app.utils.email_alerts import email_alert
from app.utils.sms_alerts import sms_alert

# from app.utils.db import SessionLocal
# from app.models.log import Log

# needed for the llava compare
os.environ["TOKENIZERS_PARALLELISM"] = "false"

"""
class SQLAlchemyHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.session = scoped_session(SessionLocal)

    def emit(self, record):
        log_entry = Log(
            level=record.levelname,
            message=record.getMessage(),
            source=record.name
        )
        self.session.add(log_entry)
        self.session.commit()
"""


def create_app(watchdog=True, schedule=True):
    """Create and configure the Flask application.

    This function sets up the entire Flask application, including:
    - Initializing the Flask app
    - Setting up configuration and secret key
    - Creating necessary directories
    - Initializing routes
    - Setting up the scheduler for various tasks
    - Implementing a watchdog for application monitoring

    Parameters
    ----------
    watchdog : bool, optional
        When ``True`` (the default) a background thread periodically
        polls the ``/health`` endpoint and checks the number of open file
        handles.  If either check fails it restores the last known good
        configuration using :func:`restore_config` and exits the process so
        an external supervisor can restart it.  Pass ``False`` to disable
        this thread entirely, which is useful when running unit tests.

    Returns
    -------
    Flask
        The configured Flask application instance.
    """
    from app.config import (
        SECRET_KEY,
        MAX_WORKERS,
        SCREENSHOT_DIRECTORY,
        VIDEO_DIRECTORY,
        SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY,
        SESSION_TIMEOUT_MINUTES,
    )

    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["SESSION_COOKIE_HTTPONLY"] = SESSION_COOKIE_HTTPONLY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        minutes=SESSION_TIMEOUT_MINUTES
    )
    # Set up logging
    app.logger.setLevel(logging.WARN)  # todo: read from config....

    # Ensure required directories exist
    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)

    from app.routes import init_routes

    init_routes(app)

    # Configure the scheduler executor
    if schedule is True:
        app.config["SCHEDULER_EXECUTORS"] = {
            "default": {"type": "processpool", "max_workers": MAX_WORKERS}
        }
        logging.info("Starting with %s workers" % str(MAX_WORKERS))
        scheduler.init_app(app)

    # Set up and start the scheduler
    if schedule is True and (
        os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug
    ):
        scheduler.start()
        logging.info("Initializing scheduler...")

        # Schedule tasks within the application context
        with app.app_context():
            # Clear existing schedules to prevent duplicates on app reload
            scheduler.remove_all_jobs()

            # Schedule various periodic tasks
            schedule_crawlers()  # TODO: make this a command line argument
            scheduler.add_job(
                id="compile_to_teaser",
                func=compile_to_teaser,
                trigger="interval",
                minutes=3,
            )
            scheduler.add_job(
                id="archive_screenshots",
                func=archive_screenshots,
                trigger="interval",
                minutes=1,
            )
            scheduler.add_job(
                id="retention_cleanup", func=retention_cleanup, trigger="cron", day="*"
            )
            schedule_summarization()

        # Perform initial cleanup
        retention_cleanup()
        logging.info("Initialization complete")

    # Backup the current configuration
    backup_config()

    # Set up a watchdog thread to monitor the application
    def watchdog():
        """Background health monitor.

        The thread issues requests to ``/health`` and inspects the number of
        open file handles every 10 seconds.  When either check fails it first
        restores the backed-up configuration and then exits the process so that
        an external supervisor can restart it.  A 15 minute cooldown prevents
        rapid restart loops.
        """
        last_restart_time = 0
        restart_cooldown = 900  # 15 minutes in seconds
        max_file_handles = 1000  # Adjust this value based on your system's limits

        while True:
            time.sleep(10)  # Check every 10 seconds
            if not app.debug:
                try:
                    # Check app responsiveness
                    with app.test_client() as client:
                        response = client.get("/health")
                        if response.status_code != 200:
                            raise Exception("Application is not responding correctly")

                    # Check file handle usage
                    current_process = psutil.Process()
                    open_files = current_process.open_files()
                    if len(open_files) > max_file_handles:
                        raise Exception(
                            f"Too many open file handles: {len(open_files)}"
                        )

                except Exception as e:
                    logging.error("Application error detected: %s", e)
                    current_time = time.time()
                    if current_time - last_restart_time > restart_cooldown:
                        logging.info("Attempting to restore previous configuration...")
                        try:
                            restore_config()
                        except Exception as config_error:
                            logging.error(
                                "Failed to restore configuration: %s", config_error
                            )
                        logging.info("Forcing application restart...")
                        last_restart_time = current_time
                        os._exit(1)  # Force restart the application
                    else:
                        logging.warning("Restart cooldown in effect. Skipping restart.")

    # Start the watchdog thread
    if watchdog is True:
        watchdog_thread = threading.Thread(target=watchdog)
        watchdog_thread.daemon = True
        watchdog_thread.start()
        app.watchdog_thread = watchdog_thread

    # Start collecting metrics
    from .utils.scheduling import start_metrics_collection

    start_metrics_collection()

    start_log_caching()

    # Send alerts when the application starts
    email_alert(
        "Application Start", "The Glimpser application has been started successfully."
    )
    sms_alert(
        "Application Start", "The Glimpser application has been started successfully."
    )

    # Make scheduler accessible globally
    app.scheduler = scheduler

    return app
