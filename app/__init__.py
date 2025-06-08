# app/__init__.py

import logging
import os
import threading
import time
import sys
import psutil
from datetime import timedelta

from flask import Flask

from app.utils.retention_policy import retention_cleanup
from app.utils.scheduling import (
    schedule_crawlers,
    schedule_summarization,
    schedule_discovery,
    schedule_offline_job_processor,
    scheduler,
    start_log_caching,
    start_metrics_collection,
    stop_event,
)
from app.utils.video_archiver import archive_screenshots, compile_to_teaser
from app.config import (
    LOG_LEVEL,
    backup_config,
    restore_config,
    DISCOVERY_AUTOSTART,
    WATCHDOG_FAILURE_THRESHOLD,
    WATCHDOG_RESTART_COOLDOWN,
    WATCHDOG_MAX_FILE_HANDLES,
    WATCHDOG_CPU_THRESHOLD,
    WATCHDOG_MEMORY_THRESHOLD,
)
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


def create_app(enable_watchdog=True, schedule=True, crawlers=True):
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
    enable_watchdog : bool, optional
        When ``True`` (the default) a background thread periodically
        polls the ``/health`` endpoint and checks the number of open file
        handles.  If either check fails it restores the last known good
        configuration using :func:`restore_config` and exits the process so
        an external supervisor can restart it.  Pass ``False`` to disable
        this thread entirely, which is useful when running unit tests.

    crawlers : bool, optional
        When ``True`` (the default) crawler jobs are scheduled.  Pass
        ``False`` to skip scheduling crawlers, which is useful during
        testing or when using the application purely for playback.

    Returns
    -------
    Flask
        The configured Flask application instance.
    """
    from app.config import (
        SECRET_KEY,
        MAX_WORKERS,
        SCREENSHOT_DIRECTORY,
        SUMMARIES_DIRECTORY,
        VIDEO_DIRECTORY,
        SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY,
        SESSION_TIMEOUT_MINUTES,
        API_KEY,
    )

    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["SESSION_COOKIE_HTTPONLY"] = SESSION_COOKIE_HTTPONLY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        minutes=SESSION_TIMEOUT_MINUTES
    )
    # Set up logging using the configured level
    log_level = getattr(logging, str(LOG_LEVEL).upper(), logging.WARN)
    app.logger.setLevel(log_level)

    # Ensure required directories exist
    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(SUMMARIES_DIRECTORY, exist_ok=True)

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
            if crawlers:
                schedule_crawlers()
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
            schedule_offline_job_processor()
            if DISCOVERY_AUTOSTART:
                schedule_discovery()

        # Perform initial cleanup
        retention_cleanup()
        logging.info("Initialization complete")

    # Backup the current configuration
    backup_config()

    # Set up a watchdog thread to monitor the application
    def _watchdog_thread():
        """Background health monitor.

        The thread issues requests to ``/health`` and performs additional
        checks every 30 seconds. When CPU or memory usage exceeds configured
        thresholds the number of open file handles is inspected. If any check
        fails the previous configuration is restored and the process exits so
        an external supervisor can restart it. A 15 minute cooldown prevents
        rapid restart loops.
        """
        last_restart_time = 0
        restart_cooldown = WATCHDOG_RESTART_COOLDOWN
        max_file_handles = WATCHDOG_MAX_FILE_HANDLES
        failure_count = 0
        failure_threshold = WATCHDOG_FAILURE_THRESHOLD

        while not stop_event.is_set():
            time.sleep(30)  # Check every 30 seconds
            if not app.debug:
                try:
                    # Check app responsiveness
                    with app.test_client() as client:
                        response = client.get("/health", headers={"X-API-Key": API_KEY})
                        if response.status_code != 200:
                            raise Exception("Application is not responding correctly")

                    current_process = psutil.Process()
                    cpu_usage = psutil.cpu_percent(interval=0.1)
                    mem_usage = psutil.virtual_memory().percent

                    # Only check open files when system usage is high
                    if (
                        cpu_usage > WATCHDOG_CPU_THRESHOLD
                        or mem_usage > WATCHDOG_MEMORY_THRESHOLD
                    ):
                        open_files = current_process.open_files()
                        if len(open_files) > max_file_handles:
                            raise Exception(
                                f"Too many open file handles: {len(open_files)}"
                            )

                except Exception as e:
                    logging.error("Application error detected: %s", e)
                    failure_count += 1
                    current_time = time.time()
                    if failure_count >= failure_threshold:
                        if current_time - last_restart_time > restart_cooldown:
                            logging.info(
                                "Attempting to restore previous configuration..."
                            )
                            try:
                                restore_config()
                            except Exception as config_error:
                                logging.error(
                                    "Failed to restore configuration: %s", config_error
                                )
                            logging.info("Forcing application restart...")
                            last_restart_time = current_time
                            failure_count = 0
                            sys.exit(1)  # Force restart the application gracefully
                        else:
                            logging.warning(
                                "Restart cooldown in effect. Skipping restart."
                            )
                    else:
                        logging.warning(
                            "Health check failed (%s/%s)",
                            failure_count,
                            failure_threshold,
                        )
                else:
                    # Reset failure count on successful check
                    failure_count = 0

    def _start_background_components() -> None:
        """Initialize scheduler and monitoring in a low priority thread."""
        backup_config()

        if (
            schedule
            and (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug)
            and not scheduler.running
        ):
            scheduler.start()
            logging.info("Initializing scheduler...")

            with app.app_context():
                scheduler.remove_all_jobs()

                if crawlers:
                    schedule_crawlers()
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
                    id="retention_cleanup",
                    func=retention_cleanup,
                    trigger="cron",
                    day="*",
                )
                schedule_summarization()
                schedule_offline_job_processor()
                if DISCOVERY_AUTOSTART:
                    schedule_discovery()

            retention_cleanup()
            logging.info("Initialization complete")

        if enable_watchdog:
            watchdog_thread = threading.Thread(
                target=_watchdog_thread, name="watchdog", daemon=True
            )
            watchdog_thread.start()
            app.watchdog_thread = watchdog_thread

        if schedule:
            start_metrics_collection()

        start_log_caching()

        email_alert(
            "Application Start",
            "The Glimpser application has been started successfully.",
        )
        sms_alert(
            "Application Start",
            "The Glimpser application has been started successfully.",
        )

        app.scheduler = scheduler

    threading.Thread(
        target=_start_background_components, name="init-bg", daemon=True
    ).start()

    return app
