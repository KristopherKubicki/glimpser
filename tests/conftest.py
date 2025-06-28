import os
import sys
from pathlib import Path

import pytest
import pytest_socket
from apscheduler.schedulers.background import BackgroundScheduler

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Avoid expensive FFmpeg setup during imports
os.environ.setdefault("FFMPEG_PATH", "ffmpeg")

from app.utils.scheduling import scheduler

# Skip end-to-end tests unless explicitly enabled
os.environ.setdefault("SKIP_E2E", "1")
# Limit Hypothesis examples to speed up tests unless overridden
os.environ.setdefault("HYPOTHESIS_MAX_EXAMPLES", "10")

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
