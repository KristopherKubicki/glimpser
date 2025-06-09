import time
from unittest.mock import patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.utils.scheduling import scheduler


def test_scheduler_starts_once():
    calls = []

    original_start = scheduler.start

    def start_wrapper(*args, **kwargs):
        calls.append(1)
        return original_start(*args, **kwargs)

    with (
        patch.object(scheduler, "start", side_effect=start_wrapper),
        patch("app.__init__.schedule_crawlers"),
        patch("app.__init__.schedule_summarization"),
        patch("app.__init__.schedule_offline_job_processor"),
        patch("app.__init__.schedule_discovery"),
        patch("app.__init__.start_metrics_collection"),
        patch("app.__init__.start_log_caching"),
        patch("app.__init__.email_alert"),
        patch("app.__init__.sms_alert"),
    ):
        create_app(enable_watchdog=False, schedule=True)
        # allow background thread to run
        time.sleep(0.1)
        assert len(calls) == 1

    scheduler.shutdown(wait=False)
