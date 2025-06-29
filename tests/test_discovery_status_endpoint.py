"""Tests for discovery status endpoint."""
import os
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestDiscoveryStatusEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.scheduling.get_discovery_status")
    def test_status(self, mock_status):
        mock_status.return_value = {"status": "ready"}
        resp = self.client.get("/discovery_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ready"})


if __name__ == "__main__":
    unittest.main()
