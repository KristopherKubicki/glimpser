"""Sun-position helpers for operator camera bearing calibration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from app.utils.template_manager import parse_canonical_screenshot_timestamp


@dataclass(frozen=True)
class SunPosition:
    """Solar azimuth/elevation for a known UTC instant and camera position."""

    azimuth_degrees: float
    elevation_degrees: float
    zenith_degrees: float
    daylight: bool


FRAME_POSITION_OFFSETS: dict[str, float] = {
    "left_edge": -0.45,
    "left_third": -0.25,
    "center": 0.0,
    "right_third": 0.25,
    "right_edge": 0.45,
}


def normalize_bearing(value: float) -> float:
    """Return ``value`` wrapped into the compass range ``0 <= x < 360``."""

    return float(value) % 360.0


def bearing_to_cardinal(bearing: float) -> str:
    """Return a compact 16-wind compass label for ``bearing`` degrees."""

    directions = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    index = int((normalize_bearing(bearing) + 11.25) // 22.5) % len(directions)
    return directions[index]


def _coerce_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def solar_position(
    timestamp: datetime, latitude: float, longitude: float
) -> SunPosition:
    """Compute approximate sun position using the NOAA solar calculation.

    The precision is good enough for camera orientation work. We need degrees
    of evidence, not survey-grade astronomy.
    """

    timestamp = _coerce_utc(timestamp)
    day_of_year = int(timestamp.strftime("%j"))
    minutes = (
        timestamp.hour * 60
        + timestamp.minute
        + timestamp.second / 60
        + timestamp.microsecond / 60_000_000
    )
    fractional_hour = minutes / 60
    gamma = 2 * math.pi / 365 * (day_of_year - 1 + (fractional_hour - 12) / 24)

    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )

    true_solar_time = (minutes + equation_of_time + 4 * longitude) % 1440
    hour_angle = true_solar_time / 4 - 180
    latitude_rad = math.radians(latitude)
    hour_angle_rad = math.radians(hour_angle)

    cos_zenith = math.sin(latitude_rad) * math.sin(declination) + math.cos(
        latitude_rad
    ) * math.cos(declination) * math.cos(hour_angle_rad)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.degrees(math.acos(cos_zenith))
    elevation = 90 - zenith

    azimuth_rad = math.atan2(
        math.sin(hour_angle_rad),
        math.cos(hour_angle_rad) * math.sin(latitude_rad)
        - math.tan(declination) * math.cos(latitude_rad),
    )
    azimuth = normalize_bearing(math.degrees(azimuth_rad) + 180)

    return SunPosition(
        azimuth_degrees=round(azimuth, 2),
        elevation_degrees=round(elevation, 2),
        zenith_degrees=round(zenith, 2),
        daylight=elevation > -0.833,
    )


def frame_timestamp(camera_name: str, filename: str) -> datetime | None:
    """Return the canonical UTC timestamp embedded in a screenshot filename."""

    return parse_canonical_screenshot_timestamp(camera_name, filename)


def calibration_score(position: SunPosition) -> int:
    """Rank frames by usefulness for bearing calibration."""

    elevation = position.elevation_degrees
    if elevation < -2:
        return 0
    if -2 <= elevation < 3:
        return 20
    if 3 <= elevation <= 18:
        return 100
    if 18 < elevation <= 45:
        return 80
    if 45 < elevation <= 65:
        return 50
    return 25


def estimate_camera_bearing(
    sun_azimuth_degrees: float,
    horizontal_fov_degrees: float,
    frame_position: str,
) -> float:
    """Estimate camera center bearing from where the sun appears in the frame."""

    if frame_position not in FRAME_POSITION_OFFSETS:
        raise ValueError("invalid frame position")
    if not 10 <= horizontal_fov_degrees <= 180:
        raise ValueError("invalid horizontal field of view")

    offset = FRAME_POSITION_OFFSETS[frame_position] * horizontal_fov_degrees
    return round(normalize_bearing(sun_azimuth_degrees - offset), 2)


def sun_frame_payload(
    camera_name: str,
    filename: str,
    latitude: float,
    longitude: float,
) -> dict[str, object] | None:
    """Return UI-ready sun metadata for a screenshot frame."""

    captured_at = frame_timestamp(camera_name, filename)
    if captured_at is None:
        return None

    position = solar_position(captured_at, latitude, longitude)
    return {
        "filename": filename,
        "captured_at": captured_at.replace(tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "sun_azimuth_degrees": position.azimuth_degrees,
        "sun_elevation_degrees": position.elevation_degrees,
        "sun_cardinal": bearing_to_cardinal(position.azimuth_degrees),
        "daylight": position.daylight,
        "score": calibration_score(position),
    }


def build_sun_calibration_evidence(
    *,
    filename: str,
    captured_at: str,
    sun_azimuth_degrees: float,
    sun_elevation_degrees: float,
    frame_position: str,
    horizontal_fov_degrees: float,
    note: str = "",
) -> str:
    """Return concise evidence text suitable for ``view_pose_evidence``."""

    position_label = frame_position.replace("_", " ")
    evidence = (
        f"Sun calibration from {filename} captured {captured_at}; "
        f"computed sun azimuth {sun_azimuth_degrees:.1f} degrees, "
        f"elevation {sun_elevation_degrees:.1f} degrees; operator marked sun at "
        f"{position_label} with horizontal FOV {horizontal_fov_degrees:.1f} degrees."
    )
    note = str(note or "").strip()
    if note:
        evidence = f"{evidence} Note: {note[:240]}"
    return evidence
