"""Tests for config backup."""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class TestBackupConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.backup_path = os.path.join(self.temp_dir.name, "backup.json")
        self.env_patch = patch.dict(
            os.environ,
            {
                "GLIMPSER_DATABASE_PATH": self.db_path,
                "GLIMPSER_BACKUP_PATH": self.backup_path,
            },
        )
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
        conn.execute("INSERT INTO settings (name, value) VALUES (?, ?)", ("A", "1"))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.env_patch.stop()
        import app.config as config
        import app.utils.db as db

        importlib.reload(config)
        importlib.reload(db)
        self.temp_dir.cleanup()

    def test_backup_config_success(self):
        result = self.config.backup_config()
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.backup_path))

    def test_backup_config_raises_on_unexpected_exception(self):
        class DummySession:
            def execute(self, *a, **kw):
                raise Exception("boom")

            def close(self):
                pass

        with patch.object(self.config, "SessionLocal", return_value=DummySession()):
            with self.assertRaises(Exception):
                self.config.backup_config()


if __name__ == "__main__":
    unittest.main()
