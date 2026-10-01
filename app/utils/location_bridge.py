"""Normalize and persist shared location points for map dashboards."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.household_config import load_household_config
from app.models import LocationPoint
from app.utils.db import SessionLocal, commit_with_retry

HOUSEHOLD = load_household_config()

DEFAULT_STALE_AFTER_SECONDS = 30 * 60
MAX_METADATA_BYTES = 4096


class LocationPayloadError(ValueError):
    """Raised when an inbound location payload cannot be normalized."""


def _first_value(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return value
    return None


def _to_float(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise LocationPayloadError(f"{field_name} must be numeric") from exc


def _to_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise LocationPayloadError(f"{field_name} must be numeric") from exc


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_timestamp(value: Any) -> datetime:
    if value in (None, ""):
        return _utcnow()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC).replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        return _utcnow()
    try:
        return datetime.fromtimestamp(float(text), UTC).replace(tzinfo=None)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocationPayloadError(
            "timestamp must be ISO-8601 or epoch seconds"
        ) from exc
    if parsed.tzinfo:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _clean_token(value: Any, *, fallback: str, max_length: int = 96) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = fallback
    token = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-._:")
    return (token or fallback)[:max_length]


def _label_from_payload(payload: dict[str, Any], subject_id: str) -> str:
    raw = _first_value(payload, "label", "name", "device_name", "desc")
    if raw is None:
        raw = subject_id
    label = re.sub(r"\s+", " ", str(raw).strip())
    return (label or subject_id)[:80]


def _subject_from_payload(payload: dict[str, Any]) -> str:
    raw = _first_value(
        payload,
        "subject_id",
        "device_id",
        "device",
        "tracker_id",
        "tid",
        "vehicle_id",
        "vin",
        "topic",
    )
    if isinstance(raw, str) and "/" in raw:
        parts = [part for part in raw.split("/") if part]
        if len(parts) >= 2:
            raw = "-".join(parts[-2:])
    if raw is None:
        raw = _first_value(payload, "label", "name", "device_name")
    if raw is None:
        raise LocationPayloadError("subject_id or device_id is required")
    return _clean_token(raw, fallback="unknown-location")


def _lat_lon_from_payload(payload: dict[str, Any]) -> tuple[float, float]:
    gps = payload.get("gps")
    if isinstance(gps, (list, tuple)) and len(gps) >= 2:
        latitude = _to_float(gps[0], "latitude")
        longitude = _to_float(gps[1], "longitude")
    else:
        latitude = _to_float(
            _first_value(payload, "latitude", "lat", "_lat"), "latitude"
        )
        longitude = _to_float(
            _first_value(payload, "longitude", "lon", "lng", "_lon"),
            "longitude",
        )
    if latitude is None or longitude is None:
        raise LocationPayloadError("latitude and longitude are required")
    if not -90 <= latitude <= 90:
        raise LocationPayloadError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise LocationPayloadError("longitude must be between -180 and 180")
    return latitude, longitude


def _metadata_json(payload: dict[str, Any]) -> str:
    reserved = {
        "subject_id",
        "device_id",
        "device",
        "tracker_id",
        "tid",
        "vehicle_id",
        "vin",
        "topic",
        "label",
        "name",
        "device_name",
        "desc",
        "provider",
        "source",
        "latitude",
        "lat",
        "_lat",
        "longitude",
        "lon",
        "lng",
        "_lon",
        "gps",
        "accuracy",
        "acc",
        "horizontal_accuracy",
        "altitude",
        "alt",
        "battery",
        "battery_percent",
        "batt",
        "speed",
        "vel",
        "heading",
        "bearing",
        "course",
        "timestamp",
        "time",
        "tst",
        "updated_at",
        "stale_after_seconds",
    }
    metadata = {key: value for key, value in payload.items() if key not in reserved}
    text = json.dumps(metadata, sort_keys=True, default=str)
    if len(text.encode("utf-8")) > MAX_METADATA_BYTES:
        return json.dumps({"truncated": True}, sort_keys=True)
    return text


def normalize_location_payload(
    payload: dict[str, Any], *, provider_default: str = "android"
) -> dict[str, Any]:
    """Return a normalized latest-location dict from bridge-specific JSON."""

    if not isinstance(payload, dict):
        raise LocationPayloadError("payload must be a JSON object")
    latitude, longitude = _lat_lon_from_payload(payload)
    subject_id = _subject_from_payload(payload)
    label = _label_from_payload(payload, subject_id)
    provider = _clean_token(
        _first_value(payload, "provider", "source"),
        fallback=provider_default,
        max_length=32,
    ).lower()
    # Apply only explicitly configured, provider-scoped identity aliases.
    for alias in HOUSEHOLD.get("location_aliases", []):
        if provider == alias["provider"] and label.casefold().strip() == alias["label"]:
            key = alias["subject"]
            subject_id, label = f"hubitat-{key}", HOUSEHOLD["subjects"][key]["label"]
            break
    stale_after = (
        _to_int(payload.get("stale_after_seconds"), "stale_after_seconds")
        or DEFAULT_STALE_AFTER_SECONDS
    )
    stale_after = max(60, min(stale_after, 7 * 24 * 60 * 60))
    battery = _to_float(
        _first_value(payload, "battery_percent", "battery", "batt"),
        "battery_percent",
    )
    if battery is not None:
        battery = max(0.0, min(battery, 100.0))

    return {
        "subject_id": subject_id,
        "label": label,
        "provider": provider,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_m": _to_float(
            _first_value(payload, "accuracy", "acc", "horizontal_accuracy"),
            "accuracy_m",
        ),
        "altitude_m": _to_float(_first_value(payload, "altitude", "alt"), "altitude"),
        "battery_percent": battery,
        "speed_mps": _to_float(_first_value(payload, "speed", "vel"), "speed"),
        "heading_degrees": _to_float(
            _first_value(payload, "heading", "bearing", "course"), "heading"
        ),
        "timestamp": _parse_timestamp(
            _first_value(payload, "timestamp", "time", "tst", "updated_at")
        ),
        "stale_after_seconds": stale_after,
        "metadata_json": _metadata_json(payload),
    }


def serialize_location(point: LocationPoint, *, now: datetime | None = None) -> dict:
    """Convert a stored point into the JSON payload consumed by the map UI."""

    current = now or _utcnow()
    timestamp = point.timestamp or point.updated_at or current
    age_seconds = max(0, int((current - timestamp).total_seconds()))
    stale_after = point.stale_after_seconds or DEFAULT_STALE_AFTER_SECONDS
    return {
        "subject_id": point.subject_id,
        "label": point.label,
        "provider": point.provider,
        "latitude": point.latitude,
        "longitude": point.longitude,
        "accuracy_m": point.accuracy_m,
        "altitude_m": point.altitude_m,
        "battery_percent": point.battery_percent,
        "speed_mps": point.speed_mps,
        "heading_degrees": point.heading_degrees,
        "timestamp": timestamp.isoformat() + "Z",
        "updated_at": (point.updated_at or timestamp).isoformat() + "Z",
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after,
        "stale": age_seconds > stale_after,
        "metadata": json.loads(point.metadata_json or "{}"),
    }


def save_latest_location(
    payload: dict[str, Any], *, provider_default: str = "android"
) -> dict:
    """Normalize and upsert the latest location for a tracked subject."""

    normalized = normalize_location_payload(payload, provider_default=provider_default)
    session = SessionLocal()
    try:
        point = (
            session.query(LocationPoint)
            .filter_by(subject_id=normalized["subject_id"])
            .first()
        )
        if point is None:
            point = LocationPoint(subject_id=normalized["subject_id"])
            session.add(point)
        for key, value in normalized.items():
            setattr(point, key, value)
        point.updated_at = _utcnow()
        commit_with_retry(session)
        session.refresh(point)
        return serialize_location(point)
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


def list_latest_locations() -> list[dict]:
    """Return all tracked subjects as serialized latest-location rows."""

    session = SessionLocal()
    try:
        points = (
            session.query(LocationPoint)
            .order_by(LocationPoint.provider.asc(), LocationPoint.label.asc())
            .all()
        )
        now = _utcnow()
        return [serialize_location(point, now=now) for point in points]
    finally:
        session.close()
