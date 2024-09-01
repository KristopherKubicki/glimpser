import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import (
    EMAIL_ENABLED,
    EMAIL_SENDER,
    EMAIL_RECIPIENTS,
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_USE_TLS,
    EMAIL_USERNAME,
    EMAIL_PASSWORD,
)


def send_email_alert(subject, body):
    if not EMAIL_ENABLED.lower() == "true":
        print("Email alerts are disabled.")
        return

    sender_email = EMAIL_SENDER
    receiver_emails = EMAIL_RECIPIENTS.split(",")

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_emails)
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_SERVER, int(EMAIL_SMTP_PORT)) as server:
            if EMAIL_USE_TLS.lower() == "true":
                server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.sendmail(sender_email, receiver_emails, message.as_string())
        print("Email alert sent successfully")
    except Exception as e:
        print(f"Error sending email alert: {e}")


def email_alert(event_type, details):
    subject = f"Glimpser Alert: {event_type}"
    body = f"Event Type: {event_type}\n\nDetails:\n{details}"
    send_email_alert(subject, body)
