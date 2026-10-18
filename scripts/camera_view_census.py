#!/usr/bin/env python3
"""Build or update structured view metadata for camera templates.

The census intentionally separates facts measured from captured frames
from human/inferred fields such as direction and scene description. The
script can safely populate geometry and capture-normalization metadata
now, then operators can fill description, bearing, and confidence over
time.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from PIL import Image

from app.utils.validators import url_matches_host

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import SCREENSHOT_DIRECTORY  # noqa: E402
from app.site_locations import load_site_locations  # noqa: E402
from app.utils.template_manager import (  # noqa: E402
    Template,
    TemplateManager,
    sort_canonical_screenshot_filenames,
)
from app.utils.validators import validate_template_name  # noqa: E402

SCHEMA_VERSION = 1
STATICNESS_VALUES = {
    "unknown",
    "static",
    "slight_drift",
    "drifting",
    "ptz",
    "rotating",
    "composite",
}
LOCATION_ACCURACY_VALUES = {"", "exact", "approximate", "site", "region", "source"}
SITE_LOCATION_SEEDS = load_site_locations()


def utc_now_text() -> str:
    """Return a DB-friendly UTC timestamp."""

    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def latest_frame_path(camera_name: str, screenshot_dir: str | Path) -> Path | None:
    """Return the newest canonical still frame for ``camera_name``."""

    valid_name = validate_template_name(camera_name)
    if not valid_name:
        return None
    camera_dir = Path(screenshot_dir) / valid_name
    if not camera_dir.is_dir():
        return None
    filenames = [
        path.name
        for path in camera_dir.glob("*.png")
        if path.is_file()
        and not path.is_symlink()
        and path.name not in {"latest_camera.png", "last_clean.png"}
    ]
    ordered = sort_canonical_screenshot_filenames(valid_name, filenames)
    if not ordered:
        return None
    return camera_dir / ordered[-1]


def image_geometry(path: Path | None) -> dict[str, Any]:
    """Return measurable geometry for a latest frame path."""

    if path is None:
        return {
            "available": False,
            "width_px": None,
            "height_px": None,
            "aspect_ratio": None,
            "orientation": "unknown",
            "latest_frame": "",
            "captured_at": "",
        }
    with Image.open(path) as image:
        width, height = image.size
    if width > height:
        orientation = "landscape"
    elif height > width:
        orientation = "portrait"
    else:
        orientation = "square"
    return {
        "available": True,
        "width_px": width,
        "height_px": height,
        "aspect_ratio": round(width / height, 4) if height else None,
        "orientation": orientation,
        "latest_frame": path.name,
        "captured_at": _captured_at_from_filename(path.name),
    }


def _captured_at_from_filename(filename: str) -> str:
    """Extract ``YYYY-mm-dd HH:MM:SS`` from a canonical frame filename."""

    stem = Path(filename).stem
    match = re.search(r"(\d{14})(?:_blank)?$", stem)
    if not match:
        return ""
    stamp = match.group(1)
    try:
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""


def infer_staticness(template: dict[str, Any]) -> str:
    """Infer a coarse staticness class from existing capture settings."""

    if str(template.get("composite_view_mode") or "").strip():
        return "composite"
    if _truthy(template.get("ptz_enabled")) or str(template.get("ptz_presets") or ""):
        return "ptz"
    if str(template.get("source_template") or "").strip():
        return "composite"
    if str(template.get("horizon_level_mode") or "").strip():
        return "drifting"
    if str(template.get("stabilize_mode") or "").strip():
        return "slight_drift"
    url = str(template.get("url") or "").lower()
    if url_matches_host(url, "youtube.com") or url_matches_host(url, "youtu.be"):
        return "unknown"
    return "static"


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def parse_url_location(url: str) -> dict[str, Any] | None:
    """Extract explicit lat/lon query parameters from source URLs."""

    parsed = urlparse(str(url or ""))
    params = parse_qs(parsed.query)
    latitude = _first_float(params, ("lat", "latitude"))
    longitude = _first_float(params, ("lng", "lon", "long", "longitude"))
    if latitude is not None and longitude is not None:
        return _url_location_result(parsed, latitude, longitude)

    location = _parse_tilde_pair(params.get("cp", []))
    if location:
        return _url_location_result(parsed, *location)

    location = _parse_localdata_pair(params.get("localdata", []))
    if location:
        return _url_location_result(parsed, *location)

    location = _parse_viewport_center(params.get("viewport", []))
    if location:
        return _url_location_result(parsed, *location)

    viewport_match = re.search(r"viewport=([^/?#]+)", parsed.path)
    if viewport_match:
        location = _parse_viewport_center([viewport_match.group(1)])
        if location:
            return _url_location_result(parsed, *location)

    location = _parse_comma_pair(parsed.path)
    if location:
        return _url_location_result(parsed, *location)

    if "=" not in parsed.query:
        location = _parse_comma_pair(parsed.query)
        if location:
            return _url_location_result(parsed, *location)

    location = _parse_fragment_location(parsed.netloc, parsed.fragment)
    if location:
        return _url_location_result(parsed, *location)

    return None


def _url_location_result(
    parsed: Any, latitude: float, longitude: float
) -> dict[str, Any] | None:
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "label": parsed.netloc or "URL coordinates",
        "accuracy": "source",
        "evidence": "Coordinate parsed from the source URL.",
        "source": "url",
    }


def _first_float(params: dict[str, list[str]], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        for value in params.get(key, []):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _parse_tilde_pair(values: list[str]) -> tuple[float, float] | None:
    for value in values:
        parts = str(value).replace("%7E", "~").replace("%7e", "~").split("~")
        if len(parts) >= 2:
            pair = _coerce_lat_lon(parts[0], parts[1])
            if pair:
                return pair
    return None


def _parse_localdata_pair(values: list[str]) -> tuple[float, float] | None:
    for value in values:
        parts = str(value).split("|")
        if len(parts) >= 2:
            pair = _coerce_lat_lon(parts[0], parts[1])
            if pair:
                return pair
    return None


def _parse_viewport_center(values: list[str]) -> tuple[float, float] | None:
    for value in values:
        parts = str(value).split(":")
        if len(parts) < 4:
            continue
        try:
            north = float(parts[0])
            south = float(parts[1])
            east = float(parts[2])
            west = float(parts[3].split(",", 1)[0])
        except (TypeError, ValueError):
            continue
        return ((north + south) / 2, (east + west) / 2)
    return None


def _parse_comma_pair(value: str) -> tuple[float, float] | None:
    match = re.search(r"(?<![-.\d])(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)", value)
    if not match:
        return None
    return _coerce_lat_lon(match.group(1), match.group(2))


def _parse_fragment_location(netloc: str, fragment: str) -> tuple[float, float] | None:
    if not fragment:
        return None
    if fragment.startswith("view="):
        return _parse_comma_pair(fragment.removeprefix("view="))

    at_match = re.search(r"@(-?\d{1,3}\.\d+),(-?\d{1,2}\.\d+)", fragment)
    if at_match:
        first = float(at_match.group(1))
        second = float(at_match.group(2))
        if "firms.modaps" in netloc:
            return second, first
        return _coerce_lat_lon(first, second)

    slash_match = re.search(
        r"^\d+(?:\.\d+)?/(-?\d{1,2}\.\d+)/(-?\d{1,3}\.\d+)", fragment
    )
    if slash_match:
        return _coerce_lat_lon(slash_match.group(1), slash_match.group(2))
    return None


def _coerce_lat_lon(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def build_location_metadata(template: dict[str, Any]) -> dict[str, Any]:
    """Build physical camera/source and optional target location metadata."""

    url_location = parse_url_location(str(template.get("url") or ""))
    site_seed = infer_site_location_seed(template)
    camera_latitude = template.get("camera_latitude")
    camera_longitude = template.get("camera_longitude")
    camera_source = "template"
    if (camera_latitude is None or camera_longitude is None) and url_location:
        camera_latitude = url_location["latitude"]
        camera_longitude = url_location["longitude"]
        camera_source = "url"
    elif (camera_latitude is None or camera_longitude is None) and site_seed:
        camera_latitude = site_seed["latitude"]
        camera_longitude = site_seed["longitude"]
        camera_source = "site_seed"

    accuracy = str(template.get("camera_location_accuracy") or "").strip().lower()
    if accuracy not in LOCATION_ACCURACY_VALUES:
        accuracy = ""
    if not accuracy and camera_source == "url":
        accuracy = "source"
    if not accuracy and camera_source == "site_seed":
        accuracy = str(site_seed.get("accuracy") or "site")

    label = str(template.get("camera_location_label") or "").strip()
    if not label and url_location:
        label = str(url_location.get("label") or "URL coordinates")
    if not label and site_seed:
        label = str(site_seed.get("label") or "")

    evidence = str(template.get("camera_location_evidence") or "").strip()
    if not evidence and url_location:
        evidence = str(url_location.get("evidence") or "")
    if not evidence and site_seed:
        evidence = str(site_seed.get("evidence") or "")

    private_location = bool(
        template.get("camera_location_private") or template.get("private_camera")
    )
    if site_seed:
        private_location = private_location or bool(site_seed.get("private"))

    return {
        "camera": {
            "latitude": camera_latitude,
            "longitude": camera_longitude,
            "elevation_m": template.get("camera_elevation_m"),
            "label": label,
            "accuracy": accuracy,
            "evidence": evidence,
            "private": private_location,
            "source": camera_source if (camera_latitude is not None or label) else "",
        },
        "target": {
            "latitude": template.get("view_target_latitude"),
            "longitude": template.get("view_target_longitude"),
            "label": str(template.get("view_target_label") or ""),
        },
    }


def infer_site_location_seed(template: dict[str, Any]) -> dict[str, Any] | None:
    groups = {
        group.strip().lower()
        for group in str(template.get("groups") or "").split(",")
        if group.strip()
    }
    url = str(template.get("url") or "").lower()
    for seed in SITE_LOCATION_SEEDS:
        if groups.intersection(seed["groups"]):
            return seed
        if any(url.startswith(prefix) for prefix in seed["url_prefixes"]):
            return seed
    return None


def build_view_metadata(
    name: str,
    template: dict[str, Any],
    screenshot_dir: str | Path = SCREENSHOT_DIRECTORY,
) -> dict[str, Any]:
    """Build structured census metadata for one template."""

    frame_path = latest_frame_path(name, screenshot_dir)
    existing = _load_existing_metadata(template.get("view_metadata"))
    existing_view = existing.get("view", {})
    inferred_staticness = infer_staticness(template)
    staticness = (
        str(template.get("view_staticness") or "").strip() or inferred_staticness
    )
    if staticness not in STATICNESS_VALUES:
        staticness = inferred_staticness

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "camera": {
            "name": name,
            "groups": [
                group.strip()
                for group in str(template.get("groups") or "").split(",")
                if group.strip()
            ],
            "private_camera": bool(template.get("private_camera")),
        },
        "location": build_location_metadata(template),
        "frame": image_geometry(frame_path),
        "view": {
            "description": str(template.get("view_description") or ""),
            "direction": str(template.get("view_direction") or ""),
            "bearing_degrees": template.get("view_bearing_degrees"),
            "pitch_degrees": template.get("view_pitch_degrees"),
            "roll_degrees": template.get("view_roll_degrees"),
            "horizontal_fov_degrees": template.get("view_horizontal_fov_degrees")
            or existing_view.get("horizontal_fov_degrees"),
            "vertical_fov_degrees": template.get("view_vertical_fov_degrees")
            or existing_view.get("vertical_fov_degrees"),
            "staticness": staticness,
            "inferred_staticness": inferred_staticness,
            "confidence": str(template.get("view_pose_confidence") or "")
            or existing_view.get("confidence", "unknown"),
            "evidence": str(template.get("view_pose_evidence") or "")
            or existing_view.get("evidence", ""),
            "mount_height": str(template.get("view_mount_height") or "")
            or existing_view.get("mount_height", ""),
            "field_of_view_degrees": existing_view.get(
                "field_of_view_degrees",
                template.get("view_horizontal_fov_degrees"),
            ),
            "notes": existing_view.get("notes", ""),
        },
        "capture": {
            "rotate_degrees": int(template.get("capture_rotate_degrees") or 0),
            "crop_roi": str(template.get("capture_crop_roi") or ""),
            "lens_correction_spec": str(template.get("lens_correction_spec") or ""),
            "horizon_level_mode": str(template.get("horizon_level_mode") or ""),
            "horizon_level_roi": str(template.get("horizon_level_roi") or ""),
            "stabilize_mode": str(template.get("stabilize_mode") or ""),
            "deflicker_mode": str(template.get("deflicker_mode") or ""),
            "burst_enhance_mode": str(template.get("burst_enhance_mode") or ""),
            "composite_view_mode": str(template.get("composite_view_mode") or ""),
        },
    }
    return metadata


def _load_existing_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _load_history(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(str(raw))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def stable_history_snapshot(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return the versioned subset, excluding per-capture frame churn."""

    if not metadata:
        return {}
    frame = metadata.get("frame", {})
    return {
        "schema_version": metadata.get("schema_version"),
        "camera": metadata.get("camera", {}),
        "location": metadata.get("location", {}),
        "frame": {
            "available": frame.get("available"),
            "width_px": frame.get("width_px"),
            "height_px": frame.get("height_px"),
            "aspect_ratio": frame.get("aspect_ratio"),
            "orientation": frame.get("orientation"),
        },
        "view": metadata.get("view", {}),
        "capture": metadata.get("capture", {}),
    }


def update_metadata_history(row: Template, metadata: dict[str, Any], now: str) -> int:
    """Append a version entry when stable view/location metadata changes."""

    history = _load_history(getattr(row, "view_metadata_history", ""))
    previous_snapshot = stable_history_snapshot(
        _load_existing_metadata(getattr(row, "view_metadata", ""))
    )
    new_snapshot = stable_history_snapshot(metadata)
    version = int(getattr(row, "view_metadata_version", 0) or 0)
    if history and previous_snapshot == new_snapshot:
        return version

    version += 1
    history.append(
        {
            "version": version,
            "updated_at": now,
            "source": "camera_view_census",
            "snapshot": new_snapshot,
        }
    )
    row.view_metadata_version = version
    row.view_metadata_history = json.dumps(
        history[-50:], sort_keys=True, separators=(",", ":")
    )
    return version


def update_census(
    *,
    write: bool,
    report_path: str | Path | None = None,
    camera_names: set[str] | None = None,
    overwrite_staticness: bool = False,
    screenshot_dir: str | Path = SCREENSHOT_DIRECTORY,
) -> list[dict[str, Any]]:
    """Build census rows and optionally persist them to templates."""

    manager = TemplateManager()
    templates = manager.get_templates()
    rows: list[dict[str, Any]] = []
    now = utc_now_text()

    session = manager.get_session()
    try:
        for name, template in sorted(templates.items()):
            if camera_names and name not in camera_names:
                continue
            metadata = build_view_metadata(name, template, screenshot_dir)
            rows.append(
                {
                    "name": name,
                    "staticness": metadata["view"]["staticness"],
                    "orientation": metadata["frame"]["orientation"],
                    "width_px": metadata["frame"]["width_px"],
                    "height_px": metadata["frame"]["height_px"],
                    "camera_latitude": metadata["location"]["camera"]["latitude"],
                    "camera_longitude": metadata["location"]["camera"]["longitude"],
                    "camera_location_accuracy": metadata["location"]["camera"][
                        "accuracy"
                    ],
                    "direction": metadata["view"]["direction"],
                    "bearing_degrees": metadata["view"]["bearing_degrees"],
                    "horizontal_fov_degrees": metadata["view"][
                        "horizontal_fov_degrees"
                    ],
                    "vertical_fov_degrees": metadata["view"]["vertical_fov_degrees"],
                    "description": metadata["view"]["description"],
                    "latest_frame": metadata["frame"]["latest_frame"],
                    "captured_at": metadata["frame"]["captured_at"],
                    "metadata": metadata,
                }
            )
            if not write:
                continue
            row = session.query(Template).filter_by(name=name).first()
            if row is None:
                continue
            location = metadata["location"]["camera"]
            if (
                not (row.camera_location_evidence or "").strip()
                and location["evidence"]
            ):
                row.camera_location_evidence = location["evidence"]
            if location["source"] in {"url", "site_seed"}:
                if row.camera_latitude is None and location["latitude"] is not None:
                    row.camera_latitude = location["latitude"]
                if row.camera_longitude is None and location["longitude"] is not None:
                    row.camera_longitude = location["longitude"]
                row.camera_location_label = (
                    row.camera_location_label or location["label"]
                )
                row.camera_location_accuracy = (
                    row.camera_location_accuracy or location["accuracy"]
                )
                row.camera_location_evidence = (
                    row.camera_location_evidence or location["evidence"]
                )
                row.camera_location_private = bool(
                    row.camera_location_private or location["private"]
                )
            metadata["metadata_version"] = update_metadata_history(row, metadata, now)
            row.view_metadata = json.dumps(
                metadata, sort_keys=True, separators=(",", ":")
            )
            row.view_metadata_updated = now
            if overwrite_staticness or not (row.view_staticness or "").strip():
                row.view_staticness = metadata["view"]["staticness"]
        if write:
            session.commit()
    finally:
        session.close()

    if report_path:
        write_report(rows, report_path)
    return rows


def write_report(rows: list[dict[str, Any]], report_path: str | Path) -> None:
    """Write a markdown census report."""

    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Camera View Census",
        "",
        f"Generated: {utc_now_text()} UTC",
        "",
        "| Camera | Staticness | Orientation | Size | Location | Direction | Bearing | FOV | Description | Latest frame |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        size = (
            f"{row['width_px']}x{row['height_px']}"
            if row["width_px"] and row["height_px"]
            else ""
        )
        fov = _format_fov(
            row.get("horizontal_fov_degrees"), row.get("vertical_fov_degrees")
        )
        location = _format_location(
            row.get("camera_latitude"),
            row.get("camera_longitude"),
            row.get("camera_location_accuracy"),
        )
        lines.append(
            "| {name} | {staticness} | {orientation} | {size} | {location} | {direction} | {bearing} | {fov} | {description} | {latest_frame} |".format(
                name=_md(row["name"]),
                staticness=_md(row["staticness"]),
                orientation=_md(row["orientation"]),
                size=_md(size),
                location=_md(location),
                direction=_md(row["direction"]),
                bearing=_md(_format_degrees(row.get("bearing_degrees"))),
                fov=_md(fov),
                description=_md(row["description"]),
                latest_frame=_md(row["latest_frame"]),
            )
        )
    path.write_text("\n".join(lines) + "\n")


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _format_degrees(value: Any) -> str:
    if value in {None, ""}:
        return ""
    try:
        return f"{float(value):g} deg"
    except (TypeError, ValueError):
        return ""


def _format_fov(horizontal: Any, vertical: Any) -> str:
    h = _format_degrees(horizontal)
    v = _format_degrees(vertical)
    if h and v:
        return f"{h} x {v}"
    return h or v


def _format_location(latitude: Any, longitude: Any, accuracy: Any) -> str:
    if latitude in {None, ""} or longitude in {None, ""}:
        return ""
    try:
        location = f"{float(latitude):.5f},{float(longitude):.5f}"
    except (TypeError, ValueError):
        return ""
    accuracy_text = str(accuracy or "").strip()
    return f"{location} ({accuracy_text})" if accuracy_text else location


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="persist census metadata")
    parser.add_argument(
        "--report",
        default="data/camera_view_census.md",
        help="markdown report output path",
    )
    parser.add_argument(
        "--camera",
        action="append",
        default=[],
        help="limit to one camera name; can be repeated",
    )
    parser.add_argument(
        "--overwrite-staticness",
        action="store_true",
        help="overwrite existing view_staticness values",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    names = set(args.camera) if args.camera else None
    rows = update_census(
        write=args.write,
        report_path=args.report,
        camera_names=names,
        overwrite_staticness=args.overwrite_staticness,
    )
    action = "updated" if args.write else "scanned"
    print(f"{action} {len(rows)} camera view census rows")
    if args.report:
        print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
