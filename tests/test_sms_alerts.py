import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.sms_alerts import send_sms_alert, sms_alert


class TestSMSAlerts(unittest.TestCase):
    def test_send_sms_alert_disabled(self):
        with (
            patch("app.utils.sms_alerts.TWILIO_SID", ""),
            patch("app.utils.sms_alerts.TWILIO_TOKEN", ""),
            patch("app.utils.sms_alerts.TWILIO_NUMBER", ""),
            patch.dict(
                "sys.modules", {"twilio": MagicMock(), "twilio.rest": MagicMock()}
            ),
            patch("twilio.rest.Client") as mock_client,
        ):
            send_sms_alert("body")
            mock_client.assert_not_called()

    def test_send_sms_alert_enabled(self):
        client_instance = MagicMock()
        mock_client_class = MagicMock(return_value=client_instance)
        dummy_twilio_rest = MagicMock(Client=mock_client_class)
        with patch.dict(
            "sys.modules",
            {
                "twilio": MagicMock(rest=dummy_twilio_rest),
                "twilio.rest": dummy_twilio_rest,
            },
        ):
            with patch("app.utils.sms_alerts.TWILIO_SID", "sid"), patch(
                "app.utils.sms_alerts.TWILIO_TOKEN", "token"
            ), patch("app.utils.sms_alerts.TWILIO_NUMBER", "+123"), patch(
                "app.utils.sms_alerts.TWILIO_FROM_NUMBER", "+999"
            ):
                send_sms_alert("Body")
                mock_client_class.assert_called_once_with("sid", "token")
                client_instance.messages.create.assert_called_once_with(
                    body="Body", from_="+999", to="+123"
                )

    def test_sms_alert_wrapper(self):
        with patch("app.utils.sms_alerts.send_sms_alert") as mock_send:
            sms_alert("Test", "Details")
            mock_send.assert_called_once_with(
                "Glimpser Alert: Test\n\nDetails:\nDetails"
            )


if __name__ == "__main__":
    unittest.main()
