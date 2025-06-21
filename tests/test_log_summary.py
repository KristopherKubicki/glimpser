import datetime
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

import app.utils.scheduling as scheduling
from app.models import LogSummary
from app.utils import db


class TestLogSummary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}).start()
        import app.models as models

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
            self.assertEqual(len(rows), 1)
        finally:
            session.close()
