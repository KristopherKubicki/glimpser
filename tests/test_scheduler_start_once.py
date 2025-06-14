import os
import sys
import time
from unittest.mock import patch

from apscheduler.schedulers.background import BackgroundScheduler

from app import create_app
from app.utils.scheduling import scheduler


def test_scheduler_starts_once():
    scheduler.shutdown(wait=False)
    scheduler.set_scheduler(BackgroundScheduler())
    calls = []

    original_start = scheduler.start

    def start_wrapper(*args, **kwargs):
        calls.append(1)
        return original_start(*args, **kwargs)

    with (
        patch.object(scheduler, "start", side_effect=start_wrapper),
        patch("app.schedule_crawlers"),
        patch("app.schedule_summarization"),
        patch("app.schedule_offline_job_processor"),
        patch("app.schedule_discovery"),
        patch("app.start_metrics_collection"),
        patch("app.start_log_caching"),
        patch("app.email_alert"),
        patch("app.sms_alert"),
    ):
        create_app(enable_watchdog=False, schedule=True)
        # allow background thread to run
        time.sleep(0.1)
        assert len(calls) == 1

    scheduler.shutdown(wait=False)
    scheduler.set_scheduler(BackgroundScheduler())
