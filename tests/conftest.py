import os
import sys
from pathlib import Path

import pytest
try:
    import pytest_socket
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    import types

    pytest_socket = types.SimpleNamespace(disable_socket=lambda: None)
from apscheduler.schedulers.background import BackgroundScheduler

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
