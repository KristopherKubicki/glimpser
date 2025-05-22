import unittest
from unittest.mock import MagicMock, patch

from app.utils.email_alerts import send_email_alert, email_alert

class TestEmailAlerts(unittest.TestCase):
    @patch('app.utils.email_alerts.smtplib.SMTP')
    def test_send_email_alert_disabled(self, mock_smtp):
        with patch('app.utils.email_alerts.EMAIL_ENABLED', 'False'):
            send_email_alert('Subject', 'Body')
            mock_smtp.assert_not_called()

    @patch('app.utils.email_alerts.smtplib.SMTP')
    def test_send_email_alert_success(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        with patch.multiple('app.utils.email_alerts',
                            EMAIL_ENABLED='True',
                            EMAIL_SENDER='a@example.com',
                            EMAIL_RECIPIENTS='b@example.com',
                            EMAIL_SMTP_SERVER='smtp.example.com',
                            EMAIL_SMTP_PORT='587',
                            EMAIL_USE_TLS='True',
                            EMAIL_USERNAME='user',
                            EMAIL_PASSWORD='pass'):
            send_email_alert('Subject', 'Body')
            mock_smtp.assert_called_once_with('smtp.example.com', 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with('user', 'pass')
            mock_server.sendmail.assert_called_once()

    @patch('app.utils.email_alerts.send_email_alert')
    def test_email_alert(self, mock_send):
        email_alert('Event', 'Details')
        mock_send.assert_called_once_with('Glimpser Alert: Event', 'Event Type: Event\n\nDetails:\nDetails')

if __name__ == '__main__':
    unittest.main()
