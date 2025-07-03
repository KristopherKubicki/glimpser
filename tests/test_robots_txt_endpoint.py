import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestRobotsTxtEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def test_disallow(self):
        with patch("app.routes.config.ALLOW_BOTS", False):
            resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.decode(), "User-agent: *\nDisallow: /\n")

    def test_allow(self):
        with patch("app.routes.config.ALLOW_BOTS", True):
            resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.decode(), "User-agent: *\nAllow: /\n")


if __name__ == "__main__":
    unittest.main()
