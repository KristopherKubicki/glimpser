import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch

import app


class TestStatusDashboard(unittest.TestCase):
    def setUp(self):
        # Disable authentication before routes are registered so the
        # dashboard can be accessed without a session.
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.session_patch = patch("app.routes.session", {"user_id": 1})
        self.login_patch.start()
        self.session_patch.start()
        self.app = app.create_app(
            enable_watchdog=False, schedule=False, log_cache=False
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.session_patch.stop()

    def test_status_page_has_dashboard(self):
        resp = self.client.get("/status", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Feed Status", resp.data)


if __name__ == "__main__":
    unittest.main()
