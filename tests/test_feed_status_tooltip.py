import unittest
import sys
import os
import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import scheduling


class DummyLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class TestFeedStatusTooltip(unittest.TestCase):
    def test_tooltip_includes_log_and_offline(self):
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        templates = {
            "cam1": {
                "last_screenshot_time": now,
                "last_caption_time": now,
                "frequency": 60,
                "capture_failed": False,
                "offline_since": now,
            }
        }
        logs = [
            {
                "level": "ERROR",
                "source": "cam1",
                "timestamp": datetime.datetime.utcnow(),
                "message": "cam1 failed",
            }
        ]
        with (
            patch("app.utils.scheduling.get_templates", return_value=templates),
            patch(
                "app.utils.scheduling.log_cache",
                logs,
            ),
            patch("app.utils.scheduling.log_cache_lock", DummyLock()),
        ):
            feeds = scheduling.get_feed_status()
        tooltip = feeds[0]["tooltip"]
        self.assertIn("Offline since", tooltip)
        self.assertIn("Last log:", tooltip)


if __name__ == "__main__":
    unittest.main()
