"""Read-only household presence and conservative GPS projection from Hubitat."""

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from urllib.request import urlopen

from app.household_config import load_household_config

HOUSEHOLD = load_household_config()
HUB_URL = HOUSEHOLD.get("hub_url", "")
SUBJECTS = tuple(
    (key, spec["label"], spec["location_device"])
    for key, spec in HOUSEHOLD.get("subjects", {}).items()
    if spec.get("location_device")
)
GPS_SUBJECTS = {
    key for key, spec in HOUSEHOLD.get("subjects", {}).items() if spec.get("gps")
}
_cache: list[dict] = []
_cache_at = 0.0
_lock = Lock()


def _timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, TypeError, AttributeError):
        return None


def project_subject(
    key: str, label: str, states: dict, now: datetime | None = None
) -> dict:
    """Keep presence distinct from GPS, excluding credentials and vehicle controls."""
    now = now or datetime.now(timezone.utc)

    def value(name: str):
        state = states.get(name, {})
        return state.get("value") if isinstance(state, dict) else None

    presence = value("presence")
    result = {
        "subject_id": f"hubitat-{key}",
        "label": label,
        "provider": "hubitat",
        "presence": presence if presence in {"present", "not present"} else "unknown",
        "presence_changed_at": states.get("presence", {}).get("date"),
        "position": None,
        "position_status": "Home/away only; no GPS coordinates",
        "device_url": f"{HUB_URL}/device/edit/{dict((k, i) for k, _, i in SUBJECTS)[key]}",
    }
    if key not in GPS_SUBJECTS:
        return result
    telemetry = value("locationTelemetry")
    result["position_status"] = f"Vehicle location: {telemetry or 'unavailable'}"
    if telemetry != "present":
        return result
    try:
        lat, lon = float(value("latitude")), float(value("longitude"))
        dates = [
            _timestamp(states.get(n, {}).get("date")) for n in ("latitude", "longitude")
        ]
        if not all(dates) or not math.isfinite(lat) or not math.isfinite(lon):
            return result
        timestamp = min(dates)
        age = (now - timestamp).total_seconds()
        if not (-85 <= lat <= 85 and -180 <= lon <= 180) or not 0 <= age <= 300:
            result["position_status"] = "Vehicle coordinates stale or invalid"
            return result
        result["position"] = {
            "subject_id": result["subject_id"],
            "label": label,
            "provider": "hubitat",
            "latitude": lat,
            "longitude": lon,
            "timestamp": timestamp.isoformat(),
            "age_seconds": int(age),
            "accuracy_m": None,
            "stale": False,
        }
        result["position_status"] = "Fresh GPS coordinates"
    except (ValueError, TypeError, OverflowError):
        pass
    return result


def _read_subject(subject: tuple) -> dict:
    key, label, device_id = subject
    if not HUB_URL:
        return project_subject(key, label, {})
    try:
        with urlopen(f"{HUB_URL}/device/fullJson/{device_id}", timeout=3) as response:
            states = json.load(response).get("device", {}).get("currentStates", {})
        # Save only the projection: fullJson also contains credentials/preferences.
        return project_subject(key, label, states)
    except (OSError, ValueError, TypeError, AttributeError):
        result = project_subject(key, label, {})
        result["position_status"] = "Hubitat unavailable; presence not verified"
        return result


def household_subjects() -> list[dict]:
    """Read existing device states at most once a minute; never command devices."""
    global _cache, _cache_at
    if not HUB_URL or not SUBJECTS:
        return []
    with _lock:
        if time.monotonic() - _cache_at >= 60 or not _cache:
            with ThreadPoolExecutor(max_workers=3) as pool:
                _cache = list(pool.map(_read_subject, SUBJECTS))
            _cache_at = time.monotonic()
        subjects = deepcopy(_cache)
        for subject in subjects:
            position = subject.get("position")
            if position:
                stamp = _timestamp(position["timestamp"])
                age = (datetime.now(timezone.utc) - stamp).total_seconds()
                if not 0 <= age <= 300:
                    subject["position"] = None
                    subject["position_status"] = "Vehicle coordinates stale"
                else:
                    position["age_seconds"] = int(age)
        return subjects


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line great-circle distance, not travel distance."""
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b - a, math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def nearby_cameras(points: list[dict], cameras: list[dict]) -> list[dict]:
    """Offer distances only for recent usable GPS positions."""
    results = []
    now = datetime.now(timezone.utc)
    for point in points:
        stamp = _timestamp(point.get("timestamp"))
        if (
            not stamp
            or point.get("stale")
            or not 0 <= (now - stamp).total_seconds() <= 300
        ):
            continue
        try:
            lat, lon = float(point["latitude"]), float(point["longitude"])
            if (
                not math.isfinite(lat)
                or not math.isfinite(lon)
                or not (-85 <= lat <= 85 and -180 <= lon <= 180)
            ):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        neighbors = []
        for camera in cameras:
            loc = camera.get("location")
            if not loc:
                continue
            distance = distance_meters(lat, lon, loc["lat"], loc["lon"])
            if distance <= 10000:
                neighbors.append(
                    {
                        "name": camera["name"],
                        "distance_m": round(distance),
                        "live": camera["live"],
                        "accuracy": loc.get("accuracy", "recorded location"),
                    }
                )
        neighbors.sort(key=lambda c: c["distance_m"])
        results.append(
            {
                "subject_id": point["subject_id"],
                "label": point["label"],
                "accuracy_m": point.get("accuracy_m"),
                "cameras": neighbors[:5],
            }
        )
    return results
