import importlib
import logging
import os
import tempfile
import unittest
from unittest.mock import patch

import app.config as config
import app.utils.db as db
import app.utils.scheduling as scheduling
import app as app_module
from app.models import Log


class TestLogStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.env_patch = patch.dict(
            os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}
        )
        self.env_patch.start()

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(scheduling)
        import app.models as models

        importlib.reload(models)
        importlib.reload(models.log)
        db.init_db()
        importlib.reload(app_module)
        self.create_app = app_module.create_app

        self.patcher_cache = patch("app.start_log_caching", lambda: None)
        self.patcher_metrics = patch(
            "app.start_metrics_collection",
            lambda: None,
            create=True,
        )
        self.patcher_email = patch("app.email_alert", lambda *a, **k: None)
        self.patcher_sms = patch("app.sms_alert", lambda *a, **k: None)
        for p in (
            self.patcher_cache,
            self.patcher_metrics,
            self.patcher_email,
            self.patcher_sms,
        ):
            p.start()

        self.app = self.create_app(enable_watchdog=False, schedule=False)

    def tearDown(self):
        for p in (
            self.patcher_cache,
            self.patcher_metrics,
            self.patcher_email,
            self.patcher_sms,
        ):
            p.stop()

        self.env_patch.stop()
        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(scheduling)
        import app.models as models

        importlib.reload(models)
        importlib.reload(models.log)
        self.temp_dir.cleanup()

    def test_log_records_saved(self):
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().info("stored via db")
        session = db.SessionLocal()
        try:
            messages = [row.message for row in session.query(Log).all()]
            self.assertIn("stored via db", messages)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
