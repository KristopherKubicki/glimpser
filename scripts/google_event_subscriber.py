"""Pull SDM events outbound; no publicly exposed webhook or listening port.

Run from the repository: python -m scripts.google_event_subscriber CONFIG.json.
Config: {"credentials": "/private/subscriber.json", "subscriptions":
[{"name": "example-home", "subscription": "projects/PROJECT/subscriptions/glimpser",
"profile": "example-home"}]}. Install the google-events optional dependency first.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import sys
import time
from pathlib import Path

from app.utils.google_events import EventStore, event_database

LOG = logging.getLogger("glimpser.google_events")


def camera_mapping(profile: str) -> dict[str, str]:
    """Map exact authorized enterprise/device names to current priority cameras."""
    from app.utils.google_sdm import parse_sdm_url
    from app.utils.google_sdm_profiles import resolve_profile
    from app.utils.template_manager import TemplateManager

    project = resolve_profile(profile)
    if not project:
        raise ValueError("Unknown SDM profile")
    result = {}
    for name, details in TemplateManager().get_templates().items():
        groups = {
            g.strip().lower() for g in str(details.get("groups") or "").split(",")
        }
        if (
            "priority" not in groups
            or "archive" in groups
            or details.get("private_camera")
        ):
            continue
        camera_profile, device = parse_sdm_url(str(details.get("url") or ""))
        if device and (camera_profile or "default") == profile:
            result[f"enterprises/{project.project_id}/devices/{device}"] = name
    return result


def process_messages(
    messages: list, store: EventStore, cameras: dict, stats: dict | None = None
) -> list[str]:
    """Acknowledge invalid/irrelevant messages, but only after durable valid writes."""
    ack_ids = []
    stats = stats if stats is not None else {}
    for item in messages:
        stats["received"] = stats.get("received", 0) + 1
        stats["last_message_at"] = time.time()
        ack_id = item.get("ackId")
        if not isinstance(ack_id, str):
            continue
        try:
            data = item.get("message", {}).get("data", "")
            if len(data) > 131072:
                raise ValueError("oversized event")
            payload = json.loads(base64.b64decode(data, validate=True))
        except (ValueError, TypeError, UnicodeError):
            ack_ids.append(ack_id)
            continue
        accepted = store.ingest(payload, cameras)
        if accepted:
            stats["accepted"] = stats.get("accepted", 0) + 1
            stats["last_accepted_at"] = time.time()
        ack_ids.append(ack_id)
    return ack_ids


def main() -> None:
    """Run a resilient, independently supervised Pub/Sub pull consumer."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    config = json.loads(Path(sys.argv[1]).read_text())
    credentials, _ = google.auth.load_credentials_from_file(
        config["credentials"], scopes=["https://www.googleapis.com/auth/pubsub"]
    )
    session = AuthorizedSession(credentials)
    subscriptions = config["subscriptions"]
    if not subscriptions:
        raise ValueError("No subscriptions configured")
    for entry in subscriptions:
        if not re.fullmatch(
            r"projects/[\w.-]+/subscriptions/[\w.-]+", entry["subscription"]
        ):
            raise ValueError("Invalid subscription name")
    store = EventStore(event_database())
    counters = {
        e["name"]: {"started_at": time.time(), "received": 0, "accepted": 0}
        for e in subscriptions
    }
    mappings, refreshed_at = {}, 0
    while True:
        now = time.time()
        if now - refreshed_at >= 60:
            mappings = {e["name"]: camera_mapping(e["profile"]) for e in subscriptions}
            refreshed_at = now
        failed = False
        for entry in subscriptions:
            name = entry["name"]
            url = f"https://pubsub.googleapis.com/v1/{entry['subscription']}"
            try:
                response = session.post(
                    url + ":pull",
                    json={"maxMessages": 50, "returnImmediately": True},
                    timeout=15,
                )
                response.raise_for_status()
                acks = process_messages(
                    response.json().get("receivedMessages", []),
                    store,
                    mappings[name],
                    counters[name],
                )
                if acks:
                    response = session.post(
                        url + ":acknowledge", json={"ackIds": acks}, timeout=15
                    )
                    response.raise_for_status()
                store.health(name, "connected", counters=counters[name])
            except Exception as exc:
                # Log type only: auth/HTTP exception strings may include secrets.
                LOG.warning("Subscription %s failed (%s)", name, type(exc).__name__)
                store.health(name, "unavailable", counters=counters[name])
                failed = True
        time.sleep(15 if failed else 2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
