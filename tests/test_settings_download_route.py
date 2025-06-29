"""Tests for settings download route."""
import os
import tempfile
import unittest
from unittest.mock import mock_open, patch

from flask import Flask

from app.routes import init_routes


class TestSettingsDownloadRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.backup_path = os.path.join(self.temp_dir.name, "config.json")
        self.path_patch = patch("app.routes.BACKUP_PATH", self.backup_path)
        self.path_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    @patch("builtins.open", new_callable=mock_open, read_data=b"{}")
    @patch("app.routes.backup_config", return_value=True)
    @patch("app.routes.os.path.exists", return_value=True)
    def test_download_triggers_backup(self, mock_exists, mock_backup, mock_file):
        resp = self.client.post("/settings", data={"action": "download"})
        self.assertEqual(resp.status_code, 200)
        resp.get_data()  # trigger generator
        mock_backup.assert_called_once()
        self.assertEqual(
            resp.headers.get("Content-Disposition"),
            "attachment; filename=config_backup.json",
        )


if __name__ == "__main__":
    unittest.main()
