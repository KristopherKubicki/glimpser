"""Helpers for sending email notifications."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    EMAIL_ENABLED,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS,
    EMAIL_SENDER,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_TIMEOUT,
    EMAIL_USE_TLS,
    EMAIL_USERNAME,
)


def send_email_alert(subject: str, body: str) -> None:
    """Send an email to the configured recipients.

    Parameters
    ----------
    subject : str
        Subject line for the email.
    body : str
        Plain-text body content.

    The function checks ``EMAIL_ENABLED`` before attempting to send the
    message. Connection errors are logged.
    """
    if not EMAIL_ENABLED.lower() == "true":
        logging.info("Email alerts are disabled.")
        return

    sender_email = EMAIL_SENDER
    receiver_emails = [
        recipient.strip()
        for recipient in EMAIL_RECIPIENTS.split(",")
        if recipient.strip()
    ]

    if not receiver_emails:
        logging.warning("No valid email recipients configured.")
        return

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_emails)
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(
            EMAIL_SMTP_SERVER, int(EMAIL_SMTP_PORT), timeout=EMAIL_SMTP_TIMEOUT
        ) as server:
            if EMAIL_USE_TLS.lower() == "true":
                server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.sendmail(sender_email, receiver_emails, message.as_string())
        logging.info("Email alert sent successfully")
    except Exception as e:
        logging.error("Error sending email alert: %s", e)


def email_alert(event_type: str, details: str) -> None:
    """Compose a standard alert email and send it.

    Parameters
    ----------
    event_type : str
        Identifier for the type of event.
    details : str
        Additional information about the event.
    """

    subject = f"Glimpser Alert: {event_type}"
    body = f"Event Type: {event_type}\n\nDetails:\n{details}"
    send_email_alert(subject, body)
