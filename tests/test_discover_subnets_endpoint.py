"""Tests for discover subnets endpoint."""
import os
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestDiscoverSubnetsEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch(
        "app.routes.camera_discovery._local_subnets", return_value=["192.168.0.0/24"]
    )
    def test_returns_subnets(self, mock_subnets):
        resp = self.client.get("/discover/subnets")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), ["192.168.0.0/24", "internet"])


if __name__ == "__main__":
    unittest.main()
