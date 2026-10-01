"""Shortly delayed polls run; stale polls are discarded without catch-up."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.executors.base import run_job
from apscheduler.schedulers.background import BackgroundScheduler

from app.utils import household_presence as presence


def test_presence_runs_after_brief_jitter_but_discards_stale_poll(monkeypatch):
    monkeypatch.setattr(presence.hub, "HUB_URL", "https://hub.example")
    monkeypatch.setattr(
        presence,
        "SOURCES",
        ({"subject": "resident", "device": "1", "label": "Presence"},),
    )
    poll = Mock()
    monkeypatch.setattr(presence, "poll_presence", poll)
    scheduler = BackgroundScheduler()
    presence.schedule_presence(scheduler)
    scheduler.start(paused=True)
    try:
        job = scheduler.get_job("household_presence")
        assert job.coalesce and job.max_instances == 1
        events = run_job(
            job,
            "default",
            [datetime.now(timezone.utc) - timedelta(seconds=3)],
            "test.presence",
        )
        assert events[0].code == EVENT_JOB_EXECUTED
        poll.assert_called_once()
        events = run_job(
            job,
            "default",
            [datetime.now(timezone.utc) - timedelta(seconds=31)],
            "test.presence",
        )
        assert events[0].code == EVENT_JOB_MISSED
        poll.assert_called_once()
    finally:
        scheduler.shutdown()
