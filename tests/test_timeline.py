import unittest
from types import SimpleNamespace
from unittest import mock
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

    @patch("app.routes.SessionLocal")
    @patch("app.routes.template_manager.get_templates")
    @patch("app.blueprints.timeline.render_template")
    @patch("app.routes.session", {"user_id": 1})
    def test_timeline_route(
        self, mock_render_template, mock_get_templates, mock_session_local
    ):
        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return SimpleNamespace(id=1)

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def all(self):
                return [
                    SimpleNamespace(
                        content='{"1704067200": "hello"}', timestamp=1704067200
                    )
                ]

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        mock_session_local.return_value = DummySession()
        mock_get_templates.return_value = {
            "cam1": {"last_motion_time": "2024-01-01 00:00:00"}
        }

        response = self.client.get("/timeline")
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with(
            "timeline.html", events=mock.ANY, page_title="Timeline"
        )


if __name__ == "__main__":
    unittest.main()
