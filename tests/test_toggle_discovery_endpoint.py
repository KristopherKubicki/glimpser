import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestToggleDiscoveryEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.scheduling.scheduler")
    @patch("app.routes.scheduling.schedule_discovery")
    @patch("app.routes.update_setting")
    def test_start_discovery(self, mock_update, mock_schedule, mock_sched):
        mock_sched.get_job.return_value = None
        resp = self.client.post("/toggle_discovery")
        self.assertEqual(resp.status_code, 200)
        mock_schedule.assert_called_once()
        mock_update.assert_called_once_with("DISCOVERY_AUTOSTART", "True", restart=False)
        self.assertEqual(resp.get_json(), {"status": "running"})

    @patch("app.routes.scheduling.scheduler")
    @patch("app.routes.scheduling.stop_discovery")
    @patch("app.routes.update_setting")
    def test_stop_discovery(self, mock_update, mock_stop, mock_sched):
        mock_sched.get_job.return_value = object()
        resp = self.client.post("/toggle_discovery")
        self.assertEqual(resp.status_code, 200)
        mock_stop.assert_called_once()
        mock_update.assert_called_once_with("DISCOVERY_AUTOSTART", "False", restart=False)
        self.assertEqual(resp.get_json(), {"status": "stopped"})


if __name__ == "__main__":
    unittest.main()
