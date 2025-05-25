import unittest
from types import SimpleNamespace
from flask import Flask
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes, login_required


class TestRoleEnforcement(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test"
        init_routes(self.app)

        @self.app.route("/admin-only")
        @login_required("admin")
        def admin_only():
            return "ok"

        self.client = self.app.test_client()

    def test_admin_allowed(self):
        dummy_user = SimpleNamespace(id=1, username="a", role="admin")

        class DummySession:
            def query(self, model):
                return self

            def filter_by(self, **kw):
                return self

            def first(self):
                return dummy_user

            def close(self):
                pass

        with patch("app.routes.SessionLocal", return_value=DummySession()):
            with self.client.session_transaction() as sess:
                sess["user_id"] = 1
            resp = self.client.get("/admin-only")
            self.assertEqual(resp.status_code, 200)

    def test_viewer_blocked(self):
        dummy_user = SimpleNamespace(id=1, username="a", role="viewer")

        class DummySession:
            def query(self, model):
                return self

            def filter_by(self, **kw):
                return self

            def first(self):
                return dummy_user

            def close(self):
                pass

        with patch("app.routes.SessionLocal", return_value=DummySession()):
            with self.client.session_transaction() as sess:
                sess["user_id"] = 1
            resp = self.client.get("/admin-only")
            self.assertEqual(resp.status_code, 403)
