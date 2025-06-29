"""Tests for scheduler simple job."""
import time
from datetime import datetime
from unittest.mock import patch

from apscheduler.schedulers.background import BackgroundScheduler

from app import create_app
from app.utils.scheduling import scheduler


def create_flag_file(path):
    path.write_text("done")


def test_scheduler_executes_job(tmp_path):
    flag_file = tmp_path / "flag.txt"

    with (
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
        # Shut down any jobs created during app initialization. Using wait=True
        # ensures the underlying process pool has fully stopped before we
        # replace the scheduler instance.
        scheduler.shutdown(wait=True)
        scheduler.set_scheduler(
            BackgroundScheduler(executors={"default": {"type": "threadpool"}})
        )
        scheduler.start()
        scheduler.add_job(
            func=create_flag_file,
            args=(flag_file,),
            trigger="date",
            run_date=datetime.now(),
            id="test_job",
        )
        for _ in range(10):
            if flag_file.exists():
                break
            time.sleep(0.02)

    scheduler.shutdown(wait=False)
    scheduler.set_scheduler(BackgroundScheduler())

    assert flag_file.read_text() == "done"
