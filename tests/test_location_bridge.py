from datetime import datetime

import pytest

from app.utils import location_bridge


def test_normalize_standard_android_payload() -> None:
    payload = {
        "device_id": "phone k",
        "label": "K Phone",
        "provider": "android",
        "latitude": "42.0048",
        "longitude": "-87.7301",
        "accuracy": "18",
        "battery": "72",
        "timestamp": "2026-05-21T12:00:00Z",
    }

    normalized = location_bridge.normalize_location_payload(payload)

    assert normalized["subject_id"] == "phone-k"
    assert normalized["label"] == "K Phone"
    assert normalized["provider"] == "android"
    assert normalized["latitude"] == 42.0048
    assert normalized["longitude"] == -87.7301
    assert normalized["accuracy_m"] == 18.0
    assert normalized["battery_percent"] == 72.0
    assert normalized["timestamp"] == datetime(2026, 5, 21, 12, 0, 0)


def test_normalize_owntracks_style_payload() -> None:
    normalized = location_bridge.normalize_location_payload(
        {
            "topic": "owntracks/family/beach-phone",
            "lat": 38.9292,
            "lon": -74.921,
            "acc": 12,
            "batt": 55,
            "tst": 1779384000,
        }
    )

    assert normalized["subject_id"] == "family-beach-phone"
    assert normalized["provider"] == "android"
    assert normalized["accuracy_m"] == 12.0
    assert normalized["battery_percent"] == 55.0


def test_normalize_tesla_payload_uses_same_schema() -> None:
    normalized = location_bridge.normalize_location_payload(
        {
            "vehicle_id": "tesla-3",
            "name": "Tesla",
            "provider": "tesla",
            "gps": [42.0, -87.7],
            "speed": 0,
        }
    )

    assert normalized["subject_id"] == "tesla-3"
    assert normalized["label"] == "Tesla"
    assert normalized["provider"] == "tesla"
    assert normalized["speed_mps"] == 0.0


def test_normalize_rejects_bad_coordinates() -> None:
    with pytest.raises(location_bridge.LocationPayloadError):
        location_bridge.normalize_location_payload(
            {"device_id": "bad", "latitude": 120, "longitude": -87}
        )
