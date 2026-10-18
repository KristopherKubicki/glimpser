"""Native events must not confuse heartbeats or repeats with new arrivals."""

import pytest

from app.utils import knox_events
from app.utils.google_events import EventStore
from app.utils.knox_events import frames, motion_state, record_motion


@pytest.fixture(autouse=True)
def camera_allowlist(monkeypatch):
    monkeypatch.setattr(
        knox_events,
        "CAMERAS",
        {"FrontDoor": "entrance.example", "Driveway": "driveway.example"},
    )


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "invalid",
        '{"Camera": "user@host"}',
        '{"Camera": "host/path"}',
        '{"Camera": "host:80"}',
    ],
)
def test_invalid_allowlist_disables_sources(monkeypatch, raw):
    monkeypatch.setenv("GLIMPSER_KNOX_CAMERAS", raw)
    assert knox_events.configured_cameras() == {}


def test_explicit_allowlist_and_empty_default(monkeypatch):
    monkeypatch.delenv("GLIMPSER_KNOX_CAMERAS", raising=False)
    assert knox_events.configured_cameras() == {}
    monkeypatch.setenv("GLIMPSER_KNOX_CAMERAS", '{"Entrance": "CAMERA.example"}')
    assert knox_events.configured_cameras() == {"Entrance": "camera.example"}


def test_unconfigured_subscriber_does_not_start_workers(monkeypatch):
    from unittest.mock import Mock

    from scripts import knox_event_subscriber as subscriber

    monkeypatch.setattr(subscriber, "CAMERAS", {})
    pool = Mock()
    monkeypatch.setattr(subscriber, "ThreadPoolExecutor", pool)
    subscriber.main()
    pool.assert_not_called()


def xml(state="active", kind="VMD", channel="1", stamp="one"):
    return (
        f'<EventNotificationAlert xmlns="urn:test"><channelID>{channel}</channelID>'
        f"<eventType>{kind}</eventType><eventState>{state}</eventState>"
        f"<dateTime>{stamp}</dateTime></EventNotificationAlert>"
    ).encode()


def test_chunk_boundaries():
    data = b"--boundary\r\n" + xml() + b"\r\n--boundary\r\n" + xml("inactive")
    assert list(frames(data[i : i + 7] for i in range(0, len(data), 7))) == [
        xml(),
        xml("inactive"),
    ]


def test_ignore_heartbeat_and_invalid():
    for data in [
        xml(kind="videoloss"),
        xml(channel="2"),
        b"bad",
        b"<!DOCTYPE x>" + xml(),
    ]:
        assert motion_state(data) is None
    assert motion_state(xml("inactive")) == "inactive"


def test_bounded_parser():
    assert list(frames([b"x" * 70000, xml()])) == [xml()]


def test_durable_dedupe_and_burst_limit(tmp_path):
    path = tmp_path / "events.db"
    store = EventStore(path)
    assert record_motion(store, "FrontDoor", xml(), 100)
    assert not record_motion(store, "FrontDoor", xml(stamp="two"), 110)
    assert not record_motion(EventStore(path), "FrontDoor", xml(), 121)
    assert record_motion(store, "FrontDoor", xml(stamp="three"), 122)
    assert not record_motion(store, "Other", xml(), 150)
    assert not record_motion(store, "FrontDoor", xml("inactive"), 150)
    with store.connect() as db:
        assert db.execute(
            "SELECT occurred,received FROM events ORDER BY received"
        ).fetchall() == [(100, 100), (122, 122)]


def test_door_not_throttled_by_driveway(tmp_path):
    store = EventStore(tmp_path / "events.db")
    assert record_motion(store, "Driveway", xml(), 100)
    assert record_motion(store, "FrontDoor", xml(), 101)


def test_projection_keeps_capture_age_separate(tmp_path, monkeypatch):
    import time

    from app.utils import knox_events

    path = tmp_path / "events.db"
    monkeypatch.setattr(knox_events, "database", lambda: path)
    store = EventStore(path)
    assert record_motion(store, "FrontDoor", xml(), time.time())
    scene = {
        "id": "door",
        "hero": {
            "name": "FrontDoor",
            "priority_event": True,
            "last_screenshot_time": "2020-01-01 00:00:00",
        },
    }
    event = knox_events.landing_events([scene])[0]
    assert event["source"] == "knox-camera-event"
    assert event["key"].startswith("knox:FrontDoor:")
    assert scene["hero"]["last_screenshot_time"] == "2020-01-01 00:00:00"
    assert not knox_events.landing_events([])
