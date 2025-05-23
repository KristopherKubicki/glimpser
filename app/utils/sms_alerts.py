import logging

from app.config import TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMBER


def send_sms_alert(message):
    """Send an SMS alert using Twilio if credentials are configured."""
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMBER]):
        logging.info("SMS alerts are disabled.")
        return

    try:
        from twilio.rest import Client
    except Exception as exc:  # ImportError or others
        logging.error("Twilio client not available: %s", exc)
        return

    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=message, from_=TWILIO_NUMBER, to=TWILIO_NUMBER)
        logging.info("SMS alert sent successfully")
    except Exception as exc:
        logging.error("Error sending SMS alert: %s", exc)


def sms_alert(event_type, details):
    body = f"Glimpser Alert: {event_type}\n\nDetails:\n{details}"
    send_sms_alert(body)
