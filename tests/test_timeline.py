import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes
from app.utils.template_manager import clear_template_cache


class TestTimeline(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="app/templates")
        self.app.config["SECRET_KEY"] = "test"  # pragma: allowlist secret
        init_routes(self.app)
        self.client = self.app.test_client()
        clear_template_cache()
        # Keep route tests independent of LAN settings and database users.
        for target, value in (
            ("app.routes.config.SKIP_LOGIN_SUBNETS", []),
            ("app.routes.API_KEY", "timeline-test-key"),  # pragma: allowlist secret
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_timeline_redirect(self):
        response = self.client.get(
            "/timeline", headers={"X-API-Key": "timeline-test-key"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/captions?tab=history-tab",
            response.headers.get("Location", ""),
        )

    def test_timeline_requires_authentication(self):
        response = self.client.get("/timeline")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/login?next="))


if __name__ == "__main__":
    unittest.main()
