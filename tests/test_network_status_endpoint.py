import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestNetworkStatusEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["ASSET_VERSION"] = "test-version"
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch(
        "app.blueprints.network.network_state",
        return_value={"lan_ok": True, "dns_ok": True, "wan_ok": True},
    )
    @patch("app.blueprints.network.is_system_online", return_value=True)
    def test_online(self, mock_online, mock_state):
        resp = self.client.get("/network_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "online": True,
                "degraded": False,
                "internet": True,
                "lan": True,
                "dns": True,
                "wan": True,
                "asset_version": self.app.config["ASSET_VERSION"],
            },
        )

    @patch(
        "app.blueprints.network.network_state",
        return_value={"lan_ok": False, "dns_ok": False, "wan_ok": False},
    )
    @patch("app.blueprints.network.is_system_online", return_value=False)
    def test_offline(self, mock_online, mock_state):
        resp = self.client.get("/network_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "online": False,
                "degraded": False,
                "internet": False,
                "lan": False,
                "dns": False,
                "wan": False,
                "asset_version": self.app.config["ASSET_VERSION"],
            },
        )

    @patch(
        "app.blueprints.network.network_state",
        return_value={"lan_ok": True, "dns_ok": False, "wan_ok": False},
    )
    @patch("app.blueprints.network.is_system_online", return_value=False)
    def test_degraded_when_lan_is_up_but_internet_is_not(self, mock_online, mock_state):
        resp = self.client.get("/network_status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {
                "online": True,
                "degraded": True,
                "internet": False,
                "lan": True,
                "dns": False,
                "wan": False,
                "asset_version": self.app.config["ASSET_VERSION"],
            },
        )


if __name__ == "__main__":
    unittest.main()
