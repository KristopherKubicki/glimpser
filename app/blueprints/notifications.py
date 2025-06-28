from __future__ import annotations

import json
import time
from collections import deque
from typing import Any, Deque

from flask import Blueprint, Response, jsonify, request, stream_with_context


def create_blueprint() -> Blueprint:
    """Create and return the notifications blueprint."""

    import app.routes as routes
    from app.models import PushSubscription

    bp = Blueprint("notifications", __name__)

    notifications: list[dict[str, str]] = []
    MAX_NOTIFICATIONS = 100
    telemetry_events: Deque[dict[str, Any]] = deque(maxlen=1000)

    @bp.route("/send_notification", methods=["POST"])
    @routes.login_required
    def send_notification() -> Response:
        """Queue a notification for connected clients."""

        data = request.get_json(force=True)
        notifications.append(
            {
                "title": data.get("title", "Notification"),
                "body": data.get("body", ""),
            }
        )
        if len(notifications) > MAX_NOTIFICATIONS:
            notifications.pop(0)
        return jsonify({"status": "queued"})

    @bp.route("/register_push", methods=["POST"])
    @routes.login_required
    def register_push() -> Response:
        """Store a push subscription for the logged in user."""

        sub = request.get_json(force=True)
        session_db = routes.SessionLocal()
        try:
            existing = (
                session_db.query(PushSubscription)
                .filter_by(
                    endpoint=sub.get("endpoint"), user_id=routes.session["user_id"]
                )
                .first()
            )
            if not existing:
                session_db.add(
                    PushSubscription(
                        user_id=routes.session["user_id"],
                        endpoint=sub.get("endpoint"),
                        auth=sub.get("keys", {}).get("auth"),
                        p256dh=sub.get("keys", {}).get("p256dh"),
                        created_at=int(time.time()),
                    )
                )
                session_db.commit()
            return jsonify({"status": "registered"})
        finally:
            session_db.close()

    @bp.route("/unregister_push", methods=["POST"])
    @routes.login_required
    def unregister_push() -> Response:
        """Delete a push subscription for the logged in user."""

        sub = request.get_json(force=True)
        session_db = routes.SessionLocal()
        try:
            existing = (
                session_db.query(PushSubscription)
                .filter_by(
                    endpoint=sub.get("endpoint"), user_id=routes.session["user_id"]
                )
                .first()
            )
            if existing:
                session_db.delete(existing)
                session_db.commit()
            return jsonify({"status": "deleted"})
        finally:
            session_db.close()

    @bp.route("/stream_notifications")
    @routes.login_required
    def stream_notifications() -> Response:
        """Stream queued notifications using Server-Sent Events."""

        def generate(last: int = len(notifications)):
            while True:
                if last < len(notifications):
                    data = notifications[last]
                    last += 1
                    yield f"data: {json.dumps(data)}\n\n"
                time.sleep(1)

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    @bp.route("/telemetry", methods=["POST"])
    @routes.login_required
    def collect_telemetry() -> Response:
        """Collect lightweight UI telemetry events."""

        data = request.get_json(force=True)
        telemetry_events.append({"ts": int(time.time()), "data": data})
        routes.logging.info("telemetry: %s", data)
        return jsonify({"status": "ok"})

    return bp
