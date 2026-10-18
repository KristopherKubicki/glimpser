"""Location freshness must not turn stale presence into usable GPS."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from app.utils import hubitat_locations as locations


def test_projection_rejects_old_gps(monkeypatch):
    monkeypatch.setattr(locations, "SUBJECTS", (("vehicle", "Vehicle", "123"),))
    monkeypatch.setattr(locations, "GPS_SUBJECTS", {"vehicle"})
    old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    states = {
        "presence": {"value": "present"},
        "locationTelemetry": {"value": "present"},
        "latitude": {"value": "41", "date": old},
        "longitude": {"value": "-87", "date": old},
    }
    result = locations.project_subject("vehicle", "Vehicle", states)
    assert result["presence"] == "present"
    assert result["position"] is None
    assert result["position_status"] == "Vehicle coordinates stale or invalid"


def test_cached_gps_expires_without_refetch_or_cache_mutation(monkeypatch):
    monkeypatch.setattr(locations, "HUB_URL", "http://hub.invalid")
    monkeypatch.setattr(locations, "SUBJECTS", (("vehicle", "Vehicle", "123"),))
    monkeypatch.setattr(locations.time, "monotonic", lambda: 100)
    monkeypatch.setattr(locations, "_cache_at", 99)
    cached = [
        {
            "position": {
                "timestamp": (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
            }
        }
    ]
    monkeypatch.setattr(locations, "_cache", cached)
    read = Mock(side_effect=AssertionError("fresh cache must not access Hubitat"))
    monkeypatch.setattr(locations, "_read_subject", read)
    result = locations.household_subjects()
    assert result[0]["position"] is None
    assert result[0]["position_status"] == "Vehicle coordinates stale"
    assert cached[0]["position"] is not None
    read.assert_not_called()


def test_nearby_cameras_excludes_stale_and_future_positions():
    now = datetime.now(UTC)
    points = [
        {"timestamp": (now + timedelta(minutes=10)).isoformat()},
        {"timestamp": (now - timedelta(minutes=10)).isoformat()},
        {"timestamp": "invalid"},
    ]
    assert locations.nearby_cameras(points, []) == []
