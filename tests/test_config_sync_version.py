"""Tests for config sync version."""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class TestSyncVersion(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        env = {
            "GLIMPSER_DATABASE_PATH": self.db_path,
            "GLIMPSER_BACKUP_PATH": os.path.join(self.temp_dir.name, "backup.json"),
        }
        self.env_patch = patch.dict(os.environ, env)
        self.env_patch.start()

        import app.config as config
        import app.utils.db as db

        importlib.reload(config)
        importlib.reload(db)
        self.config = config

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )"""
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.env_patch.stop()
        import app.config as config
        import app.utils.db as db

        importlib.reload(config)
        importlib.reload(db)
        self.temp_dir.cleanup()

    def _get_value(self):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT value FROM settings WHERE name = 'VERSION'"
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def test_inserts_new_version_when_missing(self):
        self.config.sync_version("1.2.3")
        self.assertEqual(self._get_value(), "1.2.3")

    def test_updates_existing_version(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO settings (name, value) VALUES ('VERSION', 'old')")
        conn.commit()
        conn.close()
        self.config.sync_version("1.2.3")
        self.assertEqual(self._get_value(), "1.2.3")

    def test_skips_update_if_env_set(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO settings (name, value) VALUES ('VERSION', 'old')")
        conn.commit()
        conn.close()
        os.environ["VERSION"] = "0.0.0"
        try:
            self.config.sync_version("1.2.3")
        finally:
            del os.environ["VERSION"]
        self.assertEqual(self._get_value(), "old")


if __name__ == "__main__":
    unittest.main()
