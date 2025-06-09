import os
import sys
import importlib
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
import app.config as config
import app.utils.db as db
import app.routes as routes
from app.models import Notification
from app.utils.scheduling import scheduler


class TestNotifications(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.env_patch = patch.dict(
            os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}
        )
        self.env_patch.start()

        importlib.reload(config)
        importlib.reload(db)
        import app.models as models

        importlib.reload(models)
        importlib.reload(models.notification)
        db.init_db()
        self.orig_session_local = routes.SessionLocal
        self.orig_notification = routes.Notification
        routes.Notification = models.notification.Notification
        routes.SessionLocal = db.SessionLocal

        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        from flask import Flask

        self.app = Flask(__name__)
        routes.init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.env_patch.stop()
        import app

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(app)
        routes.SessionLocal = self.orig_session_local
        routes.Notification = self.orig_notification
        import app.models as models

        importlib.reload(models)
        importlib.reload(models.notification)
        self.temp_dir.cleanup()
        scheduler.shutdown(wait=False)

    def test_table_created(self):
        from sqlalchemy import inspect

        inspector = inspect(db.engine)
        self.assertIn("notifications", inspector.get_table_names())

    def test_send_and_manage_notifications(self):
        resp = self.client.post(
            "/send_notification", json={"title": "Hello", "body": "World"}
        )
        self.assertEqual(resp.status_code, 200)
        session = db.SessionLocal()
        try:
            note = session.query(Notification).first()
            self.assertIsNotNone(note)
            note_id = note.id
        finally:
            session.close()

        self.client.post(f"/notifications/read/{note_id}")
        session = db.SessionLocal()
        try:
            note = session.query(Notification).get(note_id)
            self.assertTrue(note.viewed)
        finally:
            session.close()

        self.client.post(f"/notifications/delete/{note_id}")
        session = db.SessionLocal()
        try:
            note = session.query(Notification).get(note_id)
            self.assertIsNone(note)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
