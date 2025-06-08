import os
import sqlite3
import sys
import tempfile
import importlib
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestSettingsRoute(unittest.TestCase):
    def setUp(self):
        # Create temporary directory and database path
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.backup_path = os.path.join(self.temp_dir.name, "backup.json")

        # Patch environment for config paths
        self.env_patch = patch.dict(
            os.environ,
            {
                "GLIMPSER_DATABASE_PATH": self.db_path,
                "GLIMPSER_BACKUP_PATH": self.backup_path,
            },
        )
        self.env_patch.start()

        # Reload modules so they pick up the new environment
        import app
        import app.config as config
        import app.utils.db as db
        import app.routes as routes

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(routes)
        importlib.reload(app)

        # Initialize the database
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, value TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()

        self.app = app.create_app(enable_watchdog=False, schedule=False)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Avoid restarting the interpreter during tests
        self.restart_patch = patch("app.routes.restart_server")
        self.restart_patch.start()
        self.chrome_patch = patch("app.routes.get_chrome_version", return_value=120)
        self.shortcut_patch = patch("app.routes.first_shortcut_path", return_value=None)
        self.chrome_patch.start()
        self.shortcut_patch.start()

    def tearDown(self):
        self.restart_patch.stop()
        self.app_context.pop()
        self.env_patch.stop()
        self.chrome_patch.stop()
        self.shortcut_patch.stop()

        # Reload modules back to default environment
        import app
        import app.config as config
        import app.utils.db as db
        import app.routes as routes

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(routes)
        importlib.reload(app)

        self.temp_dir.cleanup()

    def _get_value(self, name):
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT value FROM settings WHERE name=?", (name,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def test_add_and_delete_setting(self):
        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
        ):
            response = self.client.post(
                "/settings",
                data={"action": "add", "new_name": "TEST", "new_value": "1"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/settings", response.headers["Location"])
        self.assertEqual(self._get_value("TEST"), "1")

        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
        ):
            response = self.client.post(
                "/settings", data={"action": "delete", "name_to_delete": "TEST"}
            )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self._get_value("TEST"))

    def test_update_email_settings(self):
        payload = {
            "action": "update_email",
            "EMAIL_ENABLED": "True",
            "EMAIL_SENDER": "user@example.com",
            "EMAIL_RECIPIENTS": "dest@example.com",
            "EMAIL_SMTP_SERVER": "smtp.example.com",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_USE_TLS": "True",
            "EMAIL_USERNAME": "user",
            "EMAIL_PASSWORD": "pass",
        }
        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
        ):
            response = self.client.post("/settings", data=payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._get_value("EMAIL_SENDER"), "user@example.com")
        self.assertEqual(self._get_value("EMAIL_SMTP_PORT"), "587")

    def test_backup_and_upload(self):
        # Insert a setting to be backed up
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO settings (name, value) VALUES (?, ?)", ("A", "1"))
        conn.commit()
        conn.close()

        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
        ):
            response = self.client.post("/settings", data={"action": "backup"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(os.path.exists(self.backup_path))

        # Prepare upload with modified value
        with open(self.backup_path, "r") as f:
            data = f.read()
        import json

        config = json.loads(data)
        config["A"] = "2"
        upload_path = os.path.join(self.temp_dir.name, "upload.json")
        with open(upload_path, "w") as f:
            json.dump(config, f)

        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
        ):
            with open(upload_path, "rb") as file_data:
                response = self.client.post(
                    "/settings",
                    data={"action": "upload", "file": (file_data, "config.json")},
                    content_type="multipart/form-data",
                )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._get_value("A"), "2")

    def test_download_without_backup(self):
        """Downloading settings should not crash when no backup exists."""
        if os.path.exists(self.backup_path):
            os.remove(self.backup_path)
        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
        ):
            response = self.client.post("/settings", data={"action": "download"})
        self.assertEqual(response.status_code, 302)

    def test_notification_tests(self):
        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.login_required", lambda x: x),
            patch("app.routes.send_sms_alert") as mock_sms,
            patch("app.routes.send_email_alert") as mock_email,
        ):
            response = self.client.post("/settings", data={"action": "test_sms"})
            self.assertEqual(response.status_code, 302)
            mock_sms.assert_called_once()
            response = self.client.post("/settings", data={"action": "test_email"})
            self.assertEqual(response.status_code, 302)
            mock_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
