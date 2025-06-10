import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestSearchSuggestionsEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.Path.glob", return_value=[])
    @patch("app.routes.get_active_groups")
    @patch("app.routes.template_manager.get_templates")
    def test_search_suggestions(self, mock_get_templates, mock_get_groups, mock_glob):
        mock_get_templates.return_value = {
            "Cam1": {"name": "Cam1"},
            "Cam2": {"name": "Cam2"},
        }
        mock_get_groups.return_value = ["GroupA", "GroupB"]

        resp = self.client.get("/search_suggestions?q=cam")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), ["Cam1", "Cam2"])

    @patch("app.routes.Path.glob")
    @patch("app.routes.get_active_groups")
    @patch("app.routes.template_manager.get_templates")
    def test_search_suggestions_docs(self, mock_get_templates, mock_get_groups, mock_glob):
        mock_get_templates.return_value = {}
        mock_get_groups.return_value = []
        mock_glob.return_value = [
            Path("docs/usage.md"),
            Path("docs/faq.md"),
        ]

        resp = self.client.get("/search_suggestions?q=faq")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), ["faq"])


if __name__ == "__main__":
    unittest.main()
