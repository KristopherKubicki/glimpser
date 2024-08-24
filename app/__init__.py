# app/__init__.py

import logging
import os
import threading
import psutil

from flask import Flask, current_app
from flask_apscheduler import APScheduler

from app.utils.retention_policy import retention_cleanup
from app.utils.scheduling import schedule_crawlers, schedule_summarization, scheduler
from app.utils.video_archiver import archive_screenshots, compile_to_teaser
from app.utils.video_compressor import compress_and_cleanup
from app.config import backup_config, restore_config
from app.utils import logging_utils, scheduling

# needed for the llava compare
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def create_app():
    """
    Create and configure the Flask application.

    This function sets up the entire Flask application, including:
    - Initializing the Flask app
    - Setting up configuration and secret key
    - Creating necessary directories
    - Initializing routes
    - Setting up the scheduler for various tasks
    - Implementing a watchdog for application monitoring
    - Setting up logging and metrics collection

    Returns:
        app (Flask): The configured Flask application instance
    """
    app = Flask(__name__)
    # app.config.from_object()

    from app.config import SECRET_KEY

    app.secret_key = SECRET_KEY

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

    from app.routes import init_routes

    init_routes(app)

    # Configure the scheduler executor
    app.config["SCHEDULER_EXECUTORS"] = {
        "default": {"type": "processpool", "max_workers": MAX_WORKERS}
    }
    logging.info("Starting with %s workers" % str(MAX_WORKERS))

    scheduler.init_app(app)

    # Set up and start the scheduler
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler.start()
        logging.info("Initializing scheduler...")

        # Schedule tasks within the application context
        with app.app_context():
            # Clear existing schedules to prevent duplicates on app reload
            scheduler.remove_all_jobs()

            # Schedule various periodic tasks
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

    # Backup the current configuration
    backup_config()

    # Set up a watchdog thread to monitor the application
    def watchdog():
        """
        Enhanced watchdog function to monitor the application's health.

        This function runs in a separate thread and periodically performs
        comprehensive health checks. It takes appropriate actions based on
        the system's state, including logging, alerting, and restarting.
        """
        import time

        consecutive_failures = 0
        while True:
            time.sleep(30)  # Check every 30 seconds
            if not app.debug:
                try:
                    # Perform comprehensive health check
                    with app.test_client() as client:
                        response = client.get('/health')
                        health_data = response.get_json()

                        if response.status_code != 200 or health_data['status'] != 'healthy':
                            consecutive_failures += 1
                            logging_utils.log_warning(app, f"Health check failed. Status: {health_data['status']}")

                            # Log detailed metrics
                            for key, value in health_data.items():
                                if key != 'status':
                                    logging_utils.log_info(app, f"{key}: {value}")

                            if consecutive_failures >= 3:
                                logging_utils.log_error(app, "Multiple consecutive health check failures. Initiating recovery process.")
                                # Implement recovery actions here (e.g., restart services, clear caches)
                                restore_config()
                                os._exit(1)  # Force restart the application
                        else:
                            consecutive_failures = 0
                            logging_utils.log_info(app, "Health check passed successfully.")
                except Exception as e:
                    logging_utils.log_error(app, f"Exception during health check: {str(e)}")
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        logging_utils.log_error(app, "Multiple consecutive exceptions. Initiating recovery process.")
                        restore_config()
                        os._exit(1)  # Force restart the application

    # Start the watchdog thread
    watchdog_thread = threading.Thread(target=watchdog)
    watchdog_thread.daemon = True
    watchdog_thread.start()

    # Start collecting metrics
    scheduling.start_metrics_collection()

    # Setup logging
    logging_utils.setup_logging(app)

    return app
