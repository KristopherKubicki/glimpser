"""Utilities for sending SMS alerts via Twilio."""

import logging

from app.config import TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMBER, TWILIO_FROM_NUMBER


def send_sms_alert(message):
    """Send an SMS alert using Twilio.

    Parameters
    ----------
    message : str
        Body text for the SMS message.

    The alert is only attempted if ``TWILIO_SID``, ``TWILIO_TOKEN`` and
    ``TWILIO_NUMBER`` are all configured. Any failure is logged. The SMS is
    sent from ``TWILIO_FROM_NUMBER`` to ``TWILIO_NUMBER``.
    """
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
        from_number = TWILIO_FROM_NUMBER or TWILIO_NUMBER
        client.messages.create(body=message, from_=from_number, to=TWILIO_NUMBER)
        logging.info("SMS alert sent successfully")
    except Exception as exc:
        logging.error("Error sending SMS alert: %s", exc)


def sms_alert(event_type, details):
    """Format and send an SMS alert for an event.

    Parameters
    ----------
    event_type : str
        Identifier for the type of event.
    details : str
        Additional information about the event.
    """

    body = f"Glimpser Alert: {event_type}\n\nDetails:\n{details}"
    send_sms_alert(body)
