import datetime
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

from app.models import LogSummary
from app.utils import db, scheduling


class TestLogSummary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}).start()
        from app import models

        importlib.reload(db)
        importlib.reload(models)
        importlib.reload(models.log_summary)
        importlib.reload(scheduling)
        db.init_db()
        scheduling.SessionLocal = db.SessionLocal

    def tearDown(self):
        patch.stopall()
        self.tmpdir.cleanup()

    @patch("app.utils.scheduling.summarize", return_value='{"1": "ok"}')
    def test_summarize_recent_logs(self, mock_sum):
        now = datetime.datetime.utcnow()
        with scheduling.log_cache_lock:
            scheduling.log_cache.clear()
            scheduling.log_cache.append(
                {
                    "timestamp": now,
                    "level": "INFO",
                    "source": "system",
                    "message": "test log",
                }
            )
        scheduling.summarize_recent_logs()
        session = db.SessionLocal()
        try:
            rows = session.query(LogSummary).all()
            self.assertGreaterEqual(len(rows), 1)
        finally:
            session.close()

    @patch("app.utils.scheduling.summarize", return_value='{"1": "cam"}')
    def test_camera_log_summary(self, mock_sum):
        name = "cam1"
        now = datetime.datetime.utcnow()
        with scheduling.log_cache_lock:
            scheduling.log_cache.clear()
            scheduling.log_cache.append(
                {
                    "timestamp": now,
                    "level": "ERROR",
                    "source": "camera",
                    "message": f"{name} failed",
                }
            )
        scheduling.summarize_camera_logs(name)
        session = db.SessionLocal()
        try:
            rows = session.query(LogSummary).filter_by(camera=name).all()
            self.assertGreaterEqual(len(rows), 1)
        finally:
            session.close()

    def test_get_top_failures(self):
        now = datetime.datetime.utcnow()
        with scheduling.log_cache_lock:
            scheduling.log_cache.clear()
            scheduling.log_cache.append(
                {
                    "timestamp": now,
                    "level": "ERROR",
                    "source": "camera",
                    "message": "Capture failed for Cam1 (http://example.com)",
                }
            )
            scheduling.log_cache.append(
                {
                    "timestamp": now,
                    "level": "ERROR",
                    "source": "camera",
                    "message": "Capture failed for Cam1 (http://example.com)",
                }
            )
            scheduling.log_cache.append(
                {
                    "timestamp": now,
                    "level": "WARNING",
                    "source": "camera",
                    "message": "[LAN_OFFLINE] Capture failed for Cam1 (http://example.com)",
                }
            )
            scheduling.log_cache.append(
                {
                    "timestamp": now,
                    "level": "WARNING",
                    "source": "camera",
                    "message": "RTSP preflight blocked rtsp://10.0.0.5/stream (auth required)",
                }
            )

        with patch(
            "app.utils.scheduling.get_templates",
            return_value={"Cam1": {"url": "rtsp://user:pass@10.0.0.5/stream"}},
        ):
            results = scheduling.get_top_failures(limit=10, window_hours=24)

        counts = {(r["name"], r["reason"]): r for r in results}
        self.assertEqual(counts[("Cam1", "capture failed")]["count"], 2)
        self.assertEqual(counts[("Cam1", "capture failed (LAN offline)")]["count"], 1)
        rtsp_entry = counts[("Cam1", "auth required")]
        self.assertEqual(rtsp_entry["template_name"], "Cam1")
        self.assertEqual(rtsp_entry["url"], "rtsp://10.0.0.5/stream")
        self.assertEqual(rtsp_entry["log_query"], "Cam1")
