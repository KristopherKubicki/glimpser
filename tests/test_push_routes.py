"""Tests for push routes."""
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class DummySession:
    def __init__(self):
        self.data = []
        self.kw = None

    def query(self, model):
        self.model = model
        return self

    def filter_by(self, **kwargs):
        self.kw = kwargs
        return self

    def first(self):
        for obj in self.data:
            if all(getattr(obj, k) == v for k, v in self.kw.items()):
                return obj
        return None

    def add(self, obj):
        self.data.append(obj)

    def commit(self):
        pass

    def delete(self, obj):
        self.data.remove(obj)

    def close(self):
        pass


class TestPushRoutes(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        patch("app.routes.login_required", lambda x: x).start()
        patch("app.routes.session", {"user_id": 1}).start()
        self.session = DummySession()
        patch("app.routes.SessionLocal", return_value=self.session).start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        patch.stopall()

    def test_register_and_unregister(self):
        payload = {
            "endpoint": "ep",
            "keys": {"p256dh": "k", "auth": "a"},
        }
        resp = self.client.post("/register_push", json=payload)
        self.assertEqual(resp.get_json()["status"], "registered")
        self.assertEqual(len(self.session.data), 1)

        resp = self.client.post("/unregister_push", json=payload)
        self.assertEqual(resp.get_json()["status"], "deleted")
        self.assertEqual(len(self.session.data), 0)


if __name__ == "__main__":
    unittest.main()
