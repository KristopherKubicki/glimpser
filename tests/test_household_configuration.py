"""Private household settings are opt-in; absent settings cause no I/O."""

import json
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.household_config import load_household_config
from app.utils import caption_context as captions
from app.utils import household_presence as presence
from app.utils import hubitat_locations as hub
from app.utils import location_bridge as locations


def example_config():
    return {
        "hub_url": "https://hub.example",
        "subjects": {
            "resident": {"label": "Example Resident"},
            "vehicle": {
                "label": "Example Vehicle",
                "location_device": "2",
                "gps": True,
            },
        },
        "presence_sources": [
            {
                "subject": "resident",
                "device": "1",
                "label": "Presence",
                "heartbeat_required": True,
            }
        ],
        "arrival_cameras": ["Entrance"],
        "vehicle_caption": {
            "camera": "Entrance",
            "label": "Example Vehicle",
            "facts": "Use only verified visual evidence.",
            "device": "2",
            "network_device": "3",
        },
        "location_aliases": [
            {
                "provider": "example_provider",
                "label": "Example Alias",
                "subject": "resident",
            }
        ],
    }


def test_private_configuration_loads_only_explicit_settings(tmp_path, monkeypatch):
    path = tmp_path / "private.json"
    path.write_text(json.dumps(example_config()))
    monkeypatch.setenv("GLIMPSER_HOUSEHOLD_CONFIG", str(path))
    config = load_household_config()
    assert config["subjects"]["vehicle"]["gps"] is True
    assert config["presence_sources"][0]["heartbeat_required"] is True
    assert config["location_aliases"][0]["label"] == "example alias"


@pytest.mark.parametrize(
    "invalid",
    [
        {"hub_url": "https://user:password@hub.example"},
        {"hub_url": "file:///private"},
        {"hub_url": "https://hub.example?token=secret"},
        {
            "presence_sources": [
                {"subject": "missing", "device": "1", "label": "Presence"}
            ]
        },
        {"subjects": {"resident": {"label": "Resident", "gps": "false"}}},
        {"vehicle_caption": {"camera": "../private"}},
    ],
)
def test_invalid_configuration_disables_everything(
    tmp_path, monkeypatch, caplog, invalid
):
    path = tmp_path / "private.json"
    path.write_text(json.dumps(example_config() | invalid))
    monkeypatch.setenv("GLIMPSER_HOUSEHOLD_CONFIG", str(path))
    assert load_household_config() == {}
    assert "password" not in caplog.text and "token=secret" not in caplog.text


def test_unconfigured_integrations_do_not_read_network_or_state(monkeypatch):
    monkeypatch.delenv("GLIMPSER_HOUSEHOLD_CONFIG", raising=False)
    assert load_household_config() == {}
    monkeypatch.setattr(hub, "HUB_URL", "")
    monkeypatch.setattr(hub, "SUBJECTS", ())
    monkeypatch.setattr(captions, "HUB_URL", "")
    monkeypatch.setattr(captions, "VEHICLE", {})
    monkeypatch.setattr(presence, "SOURCES", ())
    monkeypatch.setattr(presence, "SUBJECTS", {})
    forbidden = Mock(
        side_effect=AssertionError("Unconfigured integration accessed I/O")
    )
    monkeypatch.setattr(presence, "_database", forbidden)
    for module in (hub, presence, captions):
        monkeypatch.setattr(module, "urlopen", forbidden)
    scheduler = Mock()
    presence.schedule_presence(scheduler)
    scheduler.add_job.assert_not_called()
    presence.poll_presence()
    assert presence.presence_context() == {"subjects": [], "presence_events": []}
    assert hub.household_subjects() == []
    assert captions.caption_context("Entrance", []) == ""
    forbidden.assert_not_called()


def test_location_alias_is_opt_in_and_provider_scoped(monkeypatch):
    data = {
        "subject_id": "source-id",
        "label": "Example Alias",
        "provider": "example_provider",
        "latitude": 0,
        "longitude": 0,
    }
    monkeypatch.setattr(locations, "HOUSEHOLD", {})
    assert locations.normalize_location_payload(data)["subject_id"] == "source-id"
    settings = example_config()
    settings["location_aliases"][0]["label"] = "example alias"
    monkeypatch.setattr(locations, "HOUSEHOLD", settings)
    assert (
        locations.normalize_location_payload(data)["subject_id"] == "hubitat-resident"
    )
    assert (
        locations.normalize_location_payload(data | {"provider": "other"})["subject_id"]
        == "source-id"
    )


def test_disabled_subjects_do_not_reappear_in_persisted_events(tmp_path, monkeypatch):
    monkeypatch.setattr(presence.config, "DATABASE_PATH", str(tmp_path / "db"))
    monkeypatch.setattr(hub, "HUB_URL", "https://hub.example")
    monkeypatch.setattr(presence, "SUBJECTS", {"resident": "Example Resident"})
    with closing(presence._database()) as db, db:
        for key in ("resident", "removed"):
            db.execute(
                "INSERT INTO events VALUES (?, ?, ?)",
                (key, 100, json.dumps({"subject_id": f"hubitat-{key}"})),
            )
    assert presence.presence_context()["presence_events"] == [
        {"subject_id": "hubitat-resident"}
    ]


def test_configured_caption_projects_only_fresh_allowed_telemetry(monkeypatch):
    monkeypatch.setattr(captions, "VEHICLE", example_config()["vehicle_caption"])
    monkeypatch.setattr(captions, "HUB_URL", "https://hub.example")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stamp = now.isoformat()
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(
        {
            "device": {
                "currentStates": {
                    "battery": {"value": 70, "date": stamp},
                    "latitude": {"value": 1, "date": stamp},
                    "token": {"value": "must-not-leak", "date": stamp},
                }
            }
        }
    ).encode()
    monkeypatch.setattr(captions, "urlopen", Mock(return_value=response))
    text = captions.caption_context("Entrance", ["Entrance_20260101000000.png"], now)
    assert '"battery"' in text
    assert "must-not-leak" not in text and '"latitude"' not in text
    assert captions.caption_context("OtherCamera", [], now) == ""
