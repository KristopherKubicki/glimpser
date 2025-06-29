"""Tests for scheduler cleanup."""
from app.utils.scheduling import scheduler


def test_start_scheduler():
    scheduler.start()
    assert scheduler.running


def test_scheduler_reset():
    assert not scheduler.running
