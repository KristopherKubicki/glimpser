import os
import sys
import unittest
from unittest.mock import call, patch

from app.utils.push_alerts import send_push_alert


class DummySub:
    def __init__(self, endpoint: str, p256dh: str, auth: str) -> None:
        self.endpoint = endpoint
        self.p256dh = p256dh
        self.auth = auth


class DummySession:
    def __init__(self, subs):
        self.subs = subs
        self.closed = False

    def query(self, model):
        return self

    def all(self):
        return self.subs

    def close(self):
        self.closed = True


class TestPushAlerts(unittest.TestCase):
    def test_send_push_alert_success(self):
        subs = [DummySub("e1", "k1", "a1"), DummySub("e2", "k2", "a2")]
        session = DummySession(subs)
        with (
            patch("app.utils.push_alerts.VAPID_PRIVATE_KEY", "priv"),
            patch("app.utils.push_alerts.VAPID_PUBLIC_KEY", "pub"),
            patch(
                "app.utils.push_alerts.SessionLocal", return_value=session
            ) as mock_sess,
            patch("app.utils.push_alerts.webpush") as mock_webpush,
        ):
            send_push_alert("T", "B")
            mock_sess.assert_called_once()
            self.assertTrue(session.closed)
            self.assertEqual(mock_webpush.call_count, 2)
            calls = [call.kwargs for call in mock_webpush.call_args_list]
            self.assertEqual(calls[0]["subscription_info"]["endpoint"], "e1")
            self.assertEqual(calls[1]["subscription_info"]["endpoint"], "e2")

    def test_send_push_alert_disabled(self):
        with (
            patch("app.utils.push_alerts.VAPID_PRIVATE_KEY", None),
            patch("app.utils.push_alerts.VAPID_PUBLIC_KEY", None),
            patch("app.utils.push_alerts.SessionLocal") as mock_sess,
            patch("app.utils.push_alerts.webpush") as mock_webpush,
        ):
            send_push_alert("T", "B")
            mock_sess.assert_not_called()
            mock_webpush.assert_not_called()


if __name__ == "__main__":
    unittest.main()
