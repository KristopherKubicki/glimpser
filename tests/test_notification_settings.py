"""Tests for notification settings."""
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class NotificationTestMixin:
    def create_client(self, motion=True, caption=True):
        app = Flask(__name__)
        patch("app.routes.login_required", lambda x: x).start()
        patch("app.routes.session", {"user_id": 1}).start()
        patch("app.routes.SessionLocal").start()
        with (
            patch("app.config.NOTIFY_ON_MOTION", motion),
            patch("app.config.NOTIFY_ON_CAPTION", caption),
            patch("app.utils.push_alerts.send_push_alert") as push,
        ):
            init_routes(app)
            self.mock_push = push
        self.client = app.test_client()
        return app


class TestNotificationSettings(unittest.TestCase, NotificationTestMixin):
    def test_motion_setting(self):
        self.create_client(motion=False)
        resp = self.client.post(
            "/send_notification",
            json={"title": "t", "body": "b", "event": "motion"},
        )
        self.assertEqual(resp.get_json()["status"], "queued")
        self.mock_push.assert_not_called()

        self.create_client(motion=True)
        resp = self.client.post(
            "/send_notification",
            json={"title": "t", "body": "b", "event": "motion"},
        )
        self.assertEqual(resp.get_json()["status"], "queued")
        self.mock_push.assert_called_once_with("t", "b")

    def test_caption_setting(self):
        self.create_client(caption=False)
        resp = self.client.post(
            "/send_notification",
            json={"title": "t", "body": "b", "event": "caption"},
        )
        self.assertEqual(resp.get_json()["status"], "queued")
        self.mock_push.assert_not_called()

        self.create_client(caption=True)
        resp = self.client.post(
            "/send_notification",
            json={"title": "t", "body": "b", "event": "caption"},
        )
        self.assertEqual(resp.get_json()["status"], "queued")
        self.mock_push.assert_called_once_with("t", "b")


if __name__ == "__main__":
    unittest.main()
