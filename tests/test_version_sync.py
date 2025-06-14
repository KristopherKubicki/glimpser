import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


class TestVersionSync(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test.db")
        self.env_patch = patch.dict(
            os.environ,
            {
                "GLIMPSER_DATABASE_PATH": self.db_path,
                "GLIMPSER_BACKUP_PATH": os.path.join(self.tmp_dir.name, "backup.json"),
            },
        )
        self.env_patch.start()

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO settings (name, value) VALUES (?, ?)", ("VERSION", "0.1")
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp_dir.cleanup()

    def _get_version(self):
        conn = sqlite3.connect(self.db_path)
        val = conn.execute(
            "SELECT value FROM settings WHERE name='VERSION'"
        ).fetchone()[0]
        conn.close()
        return val

    def test_version_autoupdates(self):
        from importlib.metadata import version as real_version

        def fake_version(pkg):
            if pkg == "glimpser":
                return "2.0.0"
            return real_version(pkg)

        with patch("importlib.metadata.version", side_effect=fake_version):
            import app.config as config
            import app.utils.db as db

            importlib.reload(config)
            importlib.reload(db)
        self.assertEqual(config.VERSION, "2.0.0")
        self.assertEqual(self._get_version(), "2.0.0")


if __name__ == "__main__":
    unittest.main()
