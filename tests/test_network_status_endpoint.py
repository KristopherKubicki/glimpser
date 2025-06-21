import os
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestNetworkStatusEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.blueprints.network.is_system_online", return_value=True)
    def test_online(self, mock_online):
        resp = self.client.get("/network_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"online": True})

    @patch("app.blueprints.network.is_system_online", return_value=False)
    def test_offline(self, mock_online):
        resp = self.client.get("/network_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"online": False})


if __name__ == "__main__":
    unittest.main()
