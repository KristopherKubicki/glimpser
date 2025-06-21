"""Send Web Push notifications using stored subscriptions."""

import json
import logging

from pywebpush import WebPushException, webpush

from app.config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY
from app.models import PushSubscription
from app.utils.db import SessionLocal


def send_push_alert(title: str, body: str) -> None:
    """Send a push notification to all stored subscriptions.

    The ``title`` and ``body`` strings define the message payload. Each
    stored subscription receives the notification and the function returns
    ``None``.
    """
    if not (VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY):
        logging.info("Push notifications are disabled.")
        return

    session = SessionLocal()
    try:
        subs = session.query(PushSubscription).all()
        payload = json.dumps({"title": title, "body": body})
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": "mailto:none@example.com"},
                )
            except WebPushException as exc:
                logging.error("Failed to send push message: %s", exc)
    finally:
        session.close()
