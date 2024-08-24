# app/__init__.py

import logging
import os
import threading

from flask import Flask, current_app
from flask_apscheduler import APScheduler

from app.utils.retention_policy import retention_cleanup
from app.utils.scheduling import schedule_crawlers, schedule_summarization, scheduler
from app.utils.video_archiver import archive_screenshots, compile_to_teaser
from app.utils.video_compressor import compress_and_cleanup
from app.config import backup_config, restore_config

# needed for the llava compare
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def create_app():
    """
    Create and configure the Flask application.

    This function sets up the Flask app, initializes directories, configures
    the scheduler, sets up various jobs, and starts a watchdog thread.

    Returns:
        Flask: The configured Flask application instance.
    """
    app = Flask(__name__)

    # Set the secret key for the Flask app
    from app.config import SECRET_KEY
    app.secret_key = SECRET_KEY

    # Import and set up necessary directories
    from app.config import (
        MAX_WORKERS,
        SCREENSHOT_DIRECTORY,
        SUMMARIES_DIRECTORY,
        VIDEO_DIRECTORY,
    )

    # Ensure required directories exist
    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(SUMMARIES_DIRECTORY, exist_ok=True)

    # Initialize routes
    from app.routes import init_routes
    init_routes(app)

    # Configure the scheduler executor
    app.config["SCHEDULER_EXECUTORS"] = {
        "default": {"type": "processpool", "max_workers": MAX_WORKERS}
    }
    logging.info("Starting with %s workers" % str(MAX_WORKERS))

    scheduler.init_app(app)

    # Set up scheduler jobs
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler.start()
        logging.info("Initializing scheduler...")

        with app.app_context():
            # Remove existing schedules (important for app reloads in debug mode)
            scheduler.remove_all_jobs()

            # Schedule various jobs
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

        # Perform initial cleanup
        retention_cleanup()
        logging.info("Initialization complete")

    # Backup current configuration
    backup_config()

    # Set up a watchdog thread to monitor the application
    def watchdog():
        """
        Watchdog function to monitor the application's health.
        It checks the application every 10 seconds and restarts if necessary.
        """
        import time
        while True:
            time.sleep(10)  # Check every 10 seconds
            if not app.debug:
                try:
                    # Try to access a simple route to check app health
                    with app.test_client() as client:
                        response = client.get('/health')
                        if response.status_code != 200:
                            raise Exception("Application is not responding correctly")
                except Exception as e:
                    logging.error("Application error detected: %s", e)
                    logging.info("Attempting to restore previous configuration...")
                    restore_config()
                    os._exit(1)  # Force restart the application

    # Start the watchdog thread
    watchdog_thread = threading.Thread(target=watchdog)
    watchdog_thread.daemon = True
    watchdog_thread.start()

    # Start collecting metrics
    from .utils.scheduling import start_metrics_collection
    start_metrics_collection()

    return app
