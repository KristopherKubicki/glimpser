"""Device events must be timely, durable and independent of saved frame time."""

import base64
import json
from datetime import datetime, timezone

import pytest

from app.utils.google_events import EventStore, normalize_event
from scripts.google_event_subscriber import process_messages

NOW = 1790420000.0
RESOURCE = "enterprises/project/devices/door"
CAMERAS = {RESOURCE: "Front_door_doorbell"}


def payload(age=0, event_id="one", kind="CameraPerson.Person", thread="visit"):
    return {
        "eventId": event_id,
        "eventThreadId": thread,
        "timestamp": datetime.fromtimestamp(NOW - age, timezone.utc).isoformat(),
        "resourceUpdate": {
            "name": RESOURCE,
            "events": {"sdm.devices.events." + kind: {}},
        },
    }


def scene(priority=True):
    return {
        "id": "door",
        "hero": {
            "name": "Front_door_doorbell",
            "priority_event": priority,
            "last_screenshot_time": "2026-01-01 00:00:00",
        },
    }


@pytest.mark.parametrize("age", [121, 3600, -1])
def test_reject_old_or_future_activity(age):
    assert normalize_event(payload(age), CAMERAS, NOW) is None


@pytest.mark.parametrize("body", [{}, [], {"resourceUpdate": []}])
def test_reject_malformed(body):
    assert normalize_event(body, CAMERAS, NOW) is None


def test_only_mapped_activity_and_no_ended_thread():
    assert normalize_event(payload(), {}, NOW) is None
    assert normalize_event(payload(kind="CameraSound.Sound"), CAMERAS, NOW) is None
    p = payload()
    p["eventThreadState"] = "ENDED"
    assert normalize_event(p, CAMERAS, NOW) is None


def test_duplicate_survives_restart_and_ack_retry(tmp_path):
    path = tmp_path / "events.db"
    assert EventStore(path).ingest(payload(), CAMERAS, NOW)
    assert not EventStore(path).ingest(payload(), CAMERAS, NOW + 1)
    assert len(EventStore(path).landing_events([scene()], NOW + 2)) == 1


def test_out_of_order_does_not_replace_newest_and_thread_key_is_stable(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.ingest(payload(0, "new"), CAMERAS, NOW)
    store.ingest(payload(30, "old", kind="CameraMotion.Motion"), CAMERAS, NOW)
    event = store.landing_events([scene()], NOW)[0]
    assert event["kind"] == "person"
    assert event["key"] == "google:Front_door_doorbell:visit"
    store.ingest(payload(0, "updated", kind="DoorbellChime.Chime"), CAMERAS, NOW)
    assert store.landing_events([scene()], NOW)[0]["kind"] == "doorbell"
    assert store.landing_events([scene()], NOW)[0]["key"] == event["key"]


def test_scene_allowlist_priority_and_source_age(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.ingest(payload(), CAMERAS, NOW)
    assert not store.landing_events([], NOW)
    assert not store.landing_events([scene(False)], NOW)
    s = scene()
    event = store.landing_events([s], NOW)[0]
    assert event["source"] == "google-event"
    assert not event["replay_available"]
    assert s["hero"]["last_screenshot_time"] == "2026-01-01 00:00:00"
    assert not store.landing_events([s], NOW + 121)


def test_ack_only_after_commit_and_poison_messages_are_drained(tmp_path, monkeypatch):
    store = EventStore(tmp_path / "events.db")
    body = base64.b64encode(json.dumps(payload()).encode()).decode()
    monkeypatch.setattr("app.utils.google_events.time.time", lambda: NOW)
    messages = [
        {"ackId": "good", "message": {"data": body}},
        {"ackId": "bad", "message": {"data": "!"}},
    ]
    assert process_messages(messages, store, CAMERAS) == ["good", "bad"]
    assert len(store.landing_events([scene()], NOW)) == 1

    def fail(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "ingest", fail)
    with pytest.raises(OSError):
        process_messages(messages, store, CAMERAS)


def test_retention(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.ingest(payload(), CAMERAS, NOW)
    store.ingest({}, CAMERAS, NOW + 86401)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_kiosk_endpoint_uses_event_time_without_relabeling_capture(
    tmp_path, monkeypatch
):
    from flask import Flask

    from app import routes
    from app.blueprints import views
    from app.utils import google_events, household_presence

    path = tmp_path / "events.db"
    EventStore(path).ingest(payload(kind="DoorbellChime.Chime"), CAMERAS, NOW)
    monkeypatch.setattr(google_events, "event_database", lambda: path)
    monkeypatch.setattr(google_events.time, "time", lambda: NOW)
    monkeypatch.setattr(routes, "login_required", lambda f: f)
    monkeypatch.setattr(
        routes.template_manager.TemplateManager, "get_templates", lambda self: {}
    )
    s = scene()
    s["hero"]["freshness"] = {}
    monkeypatch.setattr(views, "_build_landing_scenes", lambda *args: [s])
    monkeypatch.setattr(views, "_build_landing_events", lambda *args: [])
    monkeypatch.setattr(household_presence, "arrival_events", lambda *args: [])
    app = Flask(__name__)
    app.register_blueprint(views.create_blueprint())
    client = app.test_client()
    for profile in ["office", "living"]:
        response = client.get("/landing_events?profile=" + profile)
        assert response.status_code == 200
        body = response.get_json()
        assert body["events"][0]["kind"] == "doorbell"
        assert body["capture_times"]["Front_door_doorbell"] == "2026-01-01 00:00:00"
    assert client.get("/landing_events?profile=public").get_json()["events"] == []
    monkeypatch.setattr(views, "_build_landing_scenes", lambda *args: [])
    assert client.get("/landing_events?profile=office").get_json()["events"] == []


def test_review_holds_leave_healthy_rotation_views(monkeypatch):
    from app.blueprints import views

    holds = {"ExampleUnavailable", "ExampleDuplicate"}
    monkeypatch.setattr(views, "QUARANTINED_PRESENTATION", frozenset(holds))
    monkeypatch.setattr(views, "_satellite_landing_scene", lambda *args: None)
    captured = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    templates = {
        name: {
            "groups": "chicago,skyline",
            "last_screenshot_time": captured,
            "url": "https://example.test/" + name + ".jpg",
        }
        for name in ["HealthyView", *holds]
    }
    for profile in ["office", "living"]:
        scenes = views._build_landing_scenes(
            templates,
            views.LANDING_MODE_PROFILES["medium"],
            views.LANDING_CONTENT_PROFILES[profile],
        )
        names = {s["hero"]["name"] for s in scenes}
        assert "HealthyView" in names
        assert not names.intersection(holds)


def test_delivery_counters_separate_activity_from_poison_and_duplicates(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("app.utils.google_events.time.time", lambda: NOW)
    store = EventStore(tmp_path / "events.db")
    body = base64.b64encode(json.dumps(payload()).encode()).decode()
    stats = {}
    messages = [
        {"ackId": "a", "message": {"data": body}},
        {"ackId": "b", "message": {"data": "!"}},
    ]
    assert process_messages(messages, store, CAMERAS, stats) == ["a", "b"]
    assert process_messages(messages[:1], store, CAMERAS, stats) == ["a"]
    assert stats["received"] == 3
    assert stats["accepted"] == 1
    stats["token"] = "do-not-store"
    store.health("example-home", "connected", NOW, counters=stats)
    with store.connect() as db:
        saved = json.loads(db.execute("select value from health").fetchone()[0])
    assert saved["received"] == 3
    assert saved["accepted"] == 1
    assert saved["last_message_at"] == NOW
    assert "token" not in saved
