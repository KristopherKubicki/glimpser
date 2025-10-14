import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app
from app import config, routes


class TestClockRoute(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")

        self.env_patch = patch.dict(
            os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}
        )
        self.env_patch.start()

        importlib.reload(config)
        importlib.reload(routes)

        # Disable authentication before the routes are registered so the
        # patched ``login_required`` decorator is used when the application
        # creates its route handlers.
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()

        importlib.reload(app)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, value TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()
        self.app = app.create_app(
            enable_watchdog=False, schedule=False, log_cache=False
        )
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.restart_patch = patch("app.routes.restart_server")
        self.restart_patch.start()

    def tearDown(self):
        self.restart_patch.stop()
        self.app_context.pop()
        self.login_patch.stop()
        self.env_patch.stop()
        importlib.reload(config)
        importlib.reload(routes)
        importlib.reload(app)
        self.temp_dir.cleanup()

    def test_clock_page(self):
        with patch("app.routes.session", {"user_id": 1}):
            response = self.client.get("/clock")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Clock", response.data)


if __name__ == "__main__":
    unittest.main()
