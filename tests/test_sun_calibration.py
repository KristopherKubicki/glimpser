from datetime import UTC, datetime

import pytest

from app.utils.sun_calibration import (
    bearing_to_cardinal,
    build_sun_calibration_evidence,
    calibration_score,
    estimate_camera_bearing,
    solar_position,
    sun_frame_payload,
)


def test_solar_position_identifies_daylight_over_chicago():
    position = solar_position(datetime(2026, 6, 21, 18, 0, tzinfo=UTC), 41.88, -87.63)

    assert position.daylight is True
    assert 120 <= position.azimuth_degrees <= 240
    assert position.elevation_degrees > 60


def test_solar_position_identifies_night_over_chicago():
    position = solar_position(datetime(2026, 6, 21, 4, 0, tzinfo=UTC), 41.88, -87.63)

    assert position.daylight is False
    assert position.elevation_degrees < 0
    assert calibration_score(position) == 0


@pytest.mark.parametrize(
    ("bearing", "label"),
    [(0, "N"), (44, "NE"), (90, "E"), (181, "S"), (270, "W"), (348.8, "N")],
)
def test_bearing_to_cardinal(bearing, label):
    assert bearing_to_cardinal(bearing) == label


def test_estimate_camera_bearing_offsets_sun_position_by_frame_position():
    assert estimate_camera_bearing(90, 100, "center") == 90
    assert estimate_camera_bearing(90, 100, "left_edge") == 135
    assert estimate_camera_bearing(90, 100, "right_edge") == 45


def test_estimate_camera_bearing_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="invalid frame position"):
        estimate_camera_bearing(90, 100, "top")

    with pytest.raises(ValueError, match="invalid horizontal field of view"):
        estimate_camera_bearing(90, 190, "center")


def test_sun_frame_payload_uses_canonical_frame_timestamp():
    payload = sun_frame_payload(
        "Backyard",
        "Backyard_20260621180000.png",
        41.9998,
        -87.7351,
    )

    assert payload is not None
    assert payload["filename"] == "Backyard_20260621180000.png"
    assert payload["captured_at"] == "2026-06-21T18:00:00Z"
    assert payload["score"] > 0


def test_build_sun_calibration_evidence_is_explicit():
    evidence = build_sun_calibration_evidence(
        filename="Backyard_20260621180000.png",
        captured_at="2026-06-21T18:00:00Z",
        sun_azimuth_degrees=178.9,
        sun_elevation_degrees=70.2,
        frame_position="left_third",
        horizontal_fov_degrees=110,
        note="sun glare visible on left side",
    )

    assert "Backyard_20260621180000.png" in evidence
    assert "computed sun azimuth 178.9 degrees" in evidence
    assert "operator marked sun at left third" in evidence
    assert "sun glare visible on left side" in evidence
