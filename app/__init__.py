# app/__init__.py

import logging
import os
import threading

from flask import Flask, current_app, jsonify
from flask_apscheduler import APScheduler

from app.utils.retention_policy import retention_cleanup
from app.utils.scheduling import schedule_crawlers, schedule_summarization, scheduler, get_system_metrics
from app.utils.video_archiver import archive_screenshots, compile_to_teaser
from app.utils.video_compressor import compress_and_cleanup
from app.config import backup_config, restore_config

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
        Watchdog function to monitor the application's health.

        This function runs in a separate thread and periodically checks if the
        application is responding correctly. If it detects an issue, it attempts
        to restore the previous configuration and force restarts the application.
        """
        import time
        while True:
            time.sleep(10)  # Check every 10 seconds
            if not app.debug:
                try:
                    # Try to access a simple route to check app responsiveness
                    with app.test_client() as client:
                        response = client.get('/health')
                        if response.status_code != 200:
                            raise Exception("Application is not responding correctly")
                except Exception as e:
                    logging.error("Application error detected: %s", e)
                    logging.info("Attempting to restore previous configuration...")
                    try:
                        restore_config()
                    except Exception as config_error:
                        logging.error("Failed to restore configuration: %s", config_error)
                        raise  # Re-raise the exception after logging
                    logging.info("Forcing application restart...")
                    os._exit(1)  # Force restart the application

    # Add a new route for the extended health check
    @app.route('/health')
    def health_check():
        metrics = get_system_metrics()

        # Define thresholds for nominal performance
        cpu_threshold = 80  # 80% CPU usage
        memory_threshold = 80  # 80% memory usage
        thread_threshold = 100  # 100 threads

        # Check if metrics are nominal
        is_nominal = (
            metrics['cpu_usage'] < cpu_threshold and
            metrics['memory_usage'] < memory_threshold and
            metrics['thread_count'] < thread_threshold
        )

        return jsonify({
            'status': 'healthy' if is_nominal else 'degraded',
            'metrics': metrics,
            'nominal': is_nominal
        }), 200 if is_nominal else 503

    # Start the watchdog thread
    watchdog_thread = threading.Thread(target=watchdog)
    watchdog_thread.daemon = True
    watchdog_thread.start()

    # Start collecting metrics
    from .utils.scheduling import start_metrics_collection
    start_metrics_collection()

    return app
