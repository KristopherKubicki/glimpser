import unittest
import sys
import os
import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import read_logs_from_memory


class DummyLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class TestLogFiltering(unittest.TestCase):
    def setUp(self):
        self.logs = [
            {
                "level": "INFO",
                "source": "system",
                "timestamp": datetime.datetime(2023, 1, 1, 10, 0, 0),
                "message": "System start",
            },
            {
                "level": "ERROR",
                "source": "camera",
                "timestamp": datetime.datetime(2023, 1, 2, 11, 0, 0),
                "message": "Camera error occurred",
            },
            {
                "level": "DEBUG",
                "source": "system",
                "timestamp": datetime.datetime(2023, 1, 3, 12, 0, 0),
                "message": "Debugging details",
            },
            {
                "level": "WARNING",
                "source": "camera",
                "timestamp": datetime.datetime(2023, 1, 4, 13, 0, 0),
                "message": "Camera battery low",
            },
            {
                "level": "INFO",
                "source": "user",
                "timestamp": datetime.datetime(2023, 1, 5, 14, 0, 0),
                "message": "User login",
            },
        ]

        self.patcher_cache = patch("app.routes.log_cache", self.logs)
        self.patcher_lock = patch("app.routes.log_cache_lock", DummyLock())
        self.patcher_cache.start()
        self.patcher_lock.start()

    def tearDown(self):
        self.patcher_cache.stop()
        self.patcher_lock.stop()

    def test_no_filters(self):
        result = read_logs_from_memory()
        expected = sorted(self.logs, key=lambda x: x["timestamp"], reverse=True)
        self.assertEqual(result, expected)

    def test_level_filter(self):
        result = read_logs_from_memory(level="INFO")
        expected = sorted(
            [l for l in self.logs if l["level"] == "INFO"],
            key=lambda x: x["timestamp"],
            reverse=True,
        )
        self.assertEqual(result, expected)

    def test_source_filter(self):
        result = read_logs_from_memory(source="camera")
        expected = sorted(
            [l for l in self.logs if l["source"] == "camera"],
            key=lambda x: x["timestamp"],
            reverse=True,
        )
        self.assertEqual(result, expected)

    def test_date_range_filter(self):
        start = datetime.datetime(2023, 1, 2).isoformat()
        end = datetime.datetime(2023, 1, 4, 23, 59, 59).isoformat()
        result = read_logs_from_memory(start_date=start, end_date=end)
        expected = sorted(
            [
                l
                for l in self.logs
                if datetime.datetime(2023, 1, 2)
                <= l["timestamp"]
                <= datetime.datetime(2023, 1, 4, 23, 59, 59)
            ],
            key=lambda x: x["timestamp"],
            reverse=True,
        )
        self.assertEqual(result, expected)

    def test_search_filter(self):
        result = read_logs_from_memory(search="camera")
        expected = sorted(
            [l for l in self.logs if "camera" in l["message"].lower()],
            key=lambda x: x["timestamp"],
            reverse=True,
        )
        self.assertEqual(result, expected)

    def test_combined_filters(self):
        start = datetime.datetime(2023, 1, 1).isoformat()
        end = datetime.datetime(2023, 1, 3, 23, 59, 59).isoformat()
        result = read_logs_from_memory(
            level="ERROR",
            source="camera",
            start_date=start,
            end_date=end,
            search="error",
        )
        expected = [self.logs[1]]
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
