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

    @patch("app.routes.session", {"user_id": 1})
    def test_timeline_redirect(self):
        response = self.client.get("/timeline")
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/captions?tab=history-tab",
            response.headers.get("Location", ""),
        )


if __name__ == "__main__":
    unittest.main()
