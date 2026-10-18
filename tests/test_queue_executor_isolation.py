"""A camera backlog must not occupy the maintenance executor."""

import threading

from apscheduler.events import EVENT_JOB_SUBMITTED
from apscheduler.schedulers.background import BackgroundScheduler

from app.utils.scheduling import camera_executor


def test_maintenance_runs_while_camera_executor_is_busy():
    scheduler = BackgroundScheduler(
        executors={
            "default": {"type": "threadpool", "max_workers": 1},
            "camera_captures": {"type": "threadpool", "max_workers": 1},
        }
    )
    entered, release, maintained = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def camera():
        entered.set()
        release.wait(5)

    submitted = threading.Event()
    scheduler.add_listener(
        lambda event: submitted.set() if event.job_id == "maintenance" else None,
        EVENT_JOB_SUBMITTED,
    )
    scheduler.start()
    try:
        scheduler.add_job(camera, executor=camera_executor({}))
        assert entered.wait(2)
        scheduler.add_job(maintained.set, id="maintenance")
        assert maintained.wait(1), "maintenance queued behind blocked capture"
        # Submission events fire after the scheduler removes one-shot jobs.
        # Avoid racing shutdown against that bookkeeping in this test.
        assert submitted.wait(1)
    finally:
        release.set()
        scheduler.shutdown(wait=True)
