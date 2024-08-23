# app/__init__.py

import logging
import os

from flask import Flask, current_app
from flask_apscheduler import APScheduler

from app.utils.retention_policy import retention_cleanup
from app.utils.scheduling import schedule_crawlers, schedule_summarization, scheduler
from app.routes import init_app as init_routes
from app.utils.video_archiver import archive_screenshots, compile_to_teaser
from app.utils.video_compressor import compress_and_cleanup

# needed for the llava compare
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def create_app():
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

    # Ensure the screenshot directory exists
    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(SUMMARIES_DIRECTORY, exist_ok=True)

    init_routes(app)

    # Set the executor configuration in the Flask app's config
    # should be at least as many sources
    app.config["SCHEDULER_EXECUTORS"] = {
        "default": {"type": "processpool", "max_workers": MAX_WORKERS}
    }
    logging.info(" starting with %s workers" % str(MAX_WORKERS))

    scheduler.init_app(app)

    # Scheduler setup
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler.start()
        logging.info("initializing...")

        # Schedule the crawlers upon app start
        with app.app_context():

            # remove existing schedules, particularly if the app reloads (which it does in debug mode)
            scheduler.remove_all_jobs()

            schedule_crawlers()
            # Additional scheduler setup for video archiving
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
            # scheduler.add_job(id='compress_and_cleanup', func=compress_and_cleanup, trigger='interval', hours=1)
            scheduler.add_job(
                id="retention_cleanup", func=retention_cleanup, trigger="cron", day="*"
            )
            schedule_summarization()

        # one time cleanup..
        retention_cleanup()
        logging.info("initialization complete")

    init_routes(app)

    return app
