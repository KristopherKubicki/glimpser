import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch

import app


class TestStatusDashboard(unittest.TestCase):
    def setUp(self):
        self.app = app.create_app(enable_watchdog=False, schedule=False)
        self.client = self.app.test_client()

    def test_status_page_has_dashboard(self):
        with self.app.app_context(), patch("app.routes.session", {"user_id": 1}), patch(
            "app.routes.login_required", lambda x: x
        ):
            resp = self.client.get("/status")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Feed Status", resp.data)


if __name__ == "__main__":
    unittest.main()
