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
        import importlib

        importlib.reload(db)
        importlib.reload(scheduling)
        import app.utils.template_manager as template_manager

        importlib.reload(template_manager)
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
