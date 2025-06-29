"""Tests for security headers."""
import os
import unittest

from flask import Flask

from app.routes import init_routes  # noqa: E402


class TestSecurityHeaders(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def test_headers_present(self):
        resp = self.client.get("/api/discover")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(resp.headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")
        self.assertEqual(resp.headers.get("Cache-Control"), "no-store")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
