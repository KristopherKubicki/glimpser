import os
import sys

import pytest
import pytest_socket
from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.scheduling import scheduler

# Skip end-to-end tests unless explicitly enabled
os.environ.setdefault("SKIP_E2E", "1")

# Block network access during tests to avoid accidental HTTP requests.
pytest_socket.disable_socket()


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Provide a fresh scheduler instance for each test."""
    scheduler.shutdown(wait=False)
    scheduler.set_scheduler(BackgroundScheduler())
    yield
    scheduler.shutdown(wait=False)
    scheduler.set_scheduler(BackgroundScheduler())
