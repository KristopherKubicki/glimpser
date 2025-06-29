"""Tests for email alerts."""
import os
import unittest
from unittest.mock import MagicMock, patch

from app.utils.email_alerts import email_alert, send_email_alert


class TestEmailAlerts(unittest.TestCase):
    def test_send_email_alert_disabled(self):
        with (
            patch("app.utils.email_alerts.EMAIL_ENABLED", "False"),
            patch("app.utils.email_alerts.EMAIL_SENDER", "sender@example.com"),
            patch("app.utils.email_alerts.EMAIL_RECIPIENTS", "rec@example.com"),
            patch("app.utils.email_alerts.EMAIL_SMTP_SERVER", "smtp.example.com"),
            patch("app.utils.email_alerts.EMAIL_SMTP_PORT", "587"),
            patch("app.utils.email_alerts.EMAIL_USE_TLS", "false"),
            patch("app.utils.email_alerts.EMAIL_USERNAME", "user"),
            patch("app.utils.email_alerts.EMAIL_PASSWORD", "pass"),
            patch("smtplib.SMTP") as mock_smtp,
        ):
            send_email_alert("sub", "body")
            mock_smtp.assert_not_called()

    def test_send_email_alert_enabled(self):
        smtp_mock = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = smtp_mock
        with (
            patch("smtplib.SMTP", return_value=mock_cm) as mock_smtp,
            patch("app.utils.email_alerts.EMAIL_ENABLED", "True"),
            patch("app.utils.email_alerts.EMAIL_SENDER", "sender@example.com"),
            patch(
                "app.utils.email_alerts.EMAIL_RECIPIENTS",
                "r1@example.com,r2@example.com",
            ),
            patch("app.utils.email_alerts.EMAIL_SMTP_SERVER", "smtp.example.com"),
            patch("app.utils.email_alerts.EMAIL_SMTP_PORT", "587"),
            patch("app.utils.email_alerts.EMAIL_SMTP_TIMEOUT", 5),
            patch("app.utils.email_alerts.EMAIL_USE_TLS", "true"),
            patch("app.utils.email_alerts.EMAIL_USERNAME", "user"),
            patch("app.utils.email_alerts.EMAIL_PASSWORD", "pass"),
        ):
            send_email_alert("Subject", "Body")
            mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=5)
            smtp_mock.starttls.assert_called_once()
            smtp_mock.login.assert_called_once_with("user", "pass")
            smtp_mock.sendmail.assert_called_once()
            args = smtp_mock.sendmail.call_args[0]
            self.assertEqual(args[0], "sender@example.com")
            self.assertEqual(args[1], ["r1@example.com", "r2@example.com"])
            self.assertIn("Subject: Subject", args[2])
            self.assertIn("Body", args[2])

    def test_send_email_alert_timeout(self):
        smtp_mock = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = smtp_mock
        with (
            patch("smtplib.SMTP", return_value=mock_cm) as mock_smtp,
            patch("app.utils.email_alerts.EMAIL_ENABLED", "True"),
            patch("app.utils.email_alerts.EMAIL_SENDER", "sender@example.com"),
            patch("app.utils.email_alerts.EMAIL_RECIPIENTS", "r@example.com"),
            patch("app.utils.email_alerts.EMAIL_SMTP_SERVER", "smtp.example.com"),
            patch("app.utils.email_alerts.EMAIL_SMTP_PORT", "587"),
            patch("app.utils.email_alerts.EMAIL_SMTP_TIMEOUT", 12),
            patch("app.utils.email_alerts.EMAIL_USE_TLS", "false"),
            patch("app.utils.email_alerts.EMAIL_USERNAME", "user"),
            patch("app.utils.email_alerts.EMAIL_PASSWORD", "pass"),
        ):
            send_email_alert("Subject", "Body")
            mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=12)

    def test_email_alert_wrapper(self):
        with patch("app.utils.email_alerts.send_email_alert") as mock_send:
            email_alert("Test", "Details")
            mock_send.assert_called_once_with(
                "Glimpser Alert: Test", "Event Type: Test\n\nDetails:\nDetails"
            )


if __name__ == "__main__":
    unittest.main()
