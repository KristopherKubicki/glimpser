"""Tests for config.restore_config."""

import os
import sqlite3
import importlib
import tempfile
import unittest
from unittest.mock import patch


class TestRestoreConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.backup_path = os.path.join(self.temp_dir.name, "backup.json")
        env = {
            "GLIMPSER_DATABASE_PATH": self.db_path,
            "GLIMPSER_BACKUP_PATH": self.backup_path,
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

    def test_restore_config_populates_db(self):
        data = {"FOO": "bar", "BAZ": "qux"}
        with open(self.backup_path, "w") as f:
            import json

            json.dump(data, f)

        self.config.restore_config()

        conn = sqlite3.connect(self.db_path)
        rows = dict(conn.execute("SELECT name, value FROM settings").fetchall())
        conn.close()
        self.assertEqual(rows, data)


if __name__ == "__main__":
    unittest.main()
