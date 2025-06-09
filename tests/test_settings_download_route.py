import os
import sys
import unittest
import tempfile
from flask import Flask
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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

    @patch("app.routes.send_file")
    @patch("app.routes.backup_config", return_value=True)
    @patch("app.routes.os.path.exists", return_value=True)
    def test_download_triggers_backup(self, mock_exists, mock_backup, mock_send):
        resp = self.client.post("/settings", data={"action": "download"})
        self.assertEqual(resp.status_code, 200)
        mock_backup.assert_called_once()
        mock_send.assert_called_once_with(
            self.backup_path,
            as_attachment=True,
            download_name="config_backup.json",
        )


if __name__ == "__main__":
    unittest.main()
