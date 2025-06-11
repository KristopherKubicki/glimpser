import importlib
import os
import sqlite3

# ensure repo root in path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestGetSetting(unittest.TestCase):
    def _reload_config(self, db_path):
        env = {
            "GLIMPSER_DATABASE_PATH": db_path,
            "GLIMPSER_BACKUP_PATH": os.path.join(os.path.dirname(db_path), "backup.json"),
        }
        patcher = patch.dict(os.environ, env)
        patcher.start()
        import app.config as config
        import app.utils.db as db

        importlib.reload(config)
        importlib.reload(db)
        self.addCleanup(patcher.stop)
        return config

    def test_env_variable_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            config = self._reload_config(db_path)
            os.environ["FOO"] = "bar"
            try:
                self.assertEqual(config.get_setting("FOO", "default"), "bar")
            finally:
                del os.environ["FOO"]

    def test_value_from_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                """CREATE TABLE settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, value TEXT NOT NULL)"""
            )
            conn.execute("INSERT INTO settings (name, value) VALUES (?, ?)", ("FOO", "baz"))
            conn.commit()
            conn.close()

            config = self._reload_config(db_path)
            self.assertEqual(config.get_setting("FOO", "default"), "baz")

    def test_missing_table_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            # no table created
            config = self._reload_config(db_path)
            self.assertEqual(config.get_setting("FOO", "default"), "default")


if __name__ == "__main__":
    unittest.main()
