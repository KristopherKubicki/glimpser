import unittest
from unittest.mock import patch

from app.utils.cap_alerts import cap_alert, send_cap_alert


class TestCAPAlerts(unittest.TestCase):
    def test_send_cap_alert_disabled(self):
        with (
            patch("app.utils.cap_alerts.CAP_ENDPOINT", ""),
            patch("app.utils.cap_alerts.CAP_SENDER", ""),
            patch("app.utils.cap_alerts.CAP_ENABLED", "False"),
            patch("requests.post") as mock_post,
        ):
            send_cap_alert("event", "details")
            mock_post.assert_not_called()

    def test_send_cap_alert_enabled(self):
        with (
            patch("app.utils.cap_alerts.CAP_ENDPOINT", "http://example.com"),
            patch("app.utils.cap_alerts.CAP_SENDER", "sender"),
            patch("app.utils.cap_alerts.CAP_ENABLED", "True"),
            patch("requests.post") as mock_post,
        ):
            send_cap_alert("event", "details")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertEqual(kwargs["headers"]["Content-Type"], "application/xml")
            self.assertIn(b"<event>event</event>", kwargs["data"])

    def test_cap_alert_wrapper(self):
        with patch("app.utils.cap_alerts.send_cap_alert") as mock_send:
            cap_alert("Test", "Details")
            mock_send.assert_called_once_with("Test", "Details")


if __name__ == "__main__":
    unittest.main()
