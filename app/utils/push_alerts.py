"""Send Web Push notifications using stored subscriptions."""

import json
import logging

from pywebpush import webpush, WebPushException

from app.utils.db import SessionLocal
from app.models import PushSubscription
from app.config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY


def send_push_alert(title: str, body: str) -> None:
    """Send a push notification to all stored subscriptions."""
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
