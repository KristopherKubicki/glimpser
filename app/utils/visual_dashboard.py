"""Safe presentation models for location maps and combined camera boards."""

import math
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from app.config import SCREENSHOT_DIRECTORY
from app.utils.feed_health import landing_feed_issue
from app.utils.live_caps import guess_kind
from app.utils.source_freshness import source_freshness
from app.utils.template_manager import parse_canonical_screenshot_timestamp
from app.viewer_policy import (
    CONTEXT_DESCRIPTIONS,
    CONTEXT_VIEWS,
    QUARANTINED_PRESENTATION,
    VIEWER_CONFIG,
    dashboard_matches,
)


def _saved_capture_time(name: str, recorded: str) -> str:
    """Bind a dashboard image to its actual saved filename when available."""
    latest = Path(SCREENSHOT_DIRECTORY) / name / "latest_camera.png"
    try:
        actual = parse_canonical_screenshot_timestamp(name, latest.resolve().name)
        recorded_at = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
        if (
            actual
            and abs(
                (
                    actual.replace(tzinfo=None) - recorded_at.replace(tzinfo=None)
                ).total_seconds()
            )
            <= 300
        ):
            return actual.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, TypeError):
        pass
    return recorded


def build_visual_dashboard(templates: dict, dashboard: str) -> dict:
    """Project camera data without exposing connection settings or private locations."""
    from app.routes import resolve_live_stream_url

    cameras = []
    for name, details in templates.items():
        groups = {
            s.strip().lower() for s in str(details.get("groups") or "").split(",")
        }
        if (
            "archive" in groups
            or (name in QUARANTINED_PRESENTATION and dashboard != "health")
            or not dashboard_matches(dashboard, name, details)
        ):
            continue
        issue = landing_feed_issue(details)
        location = None
        if not (
            details.get("private_camera")
            or details.get("camera_location_private")
            or "private" in groups
        ):
            try:
                lat, lon = (
                    float(details["camera_latitude"]),
                    float(details["camera_longitude"]),
                )
                if (
                    math.isfinite(lat)
                    and math.isfinite(lon)
                    and -85 <= lat <= 85
                    and -180 <= lon <= 180
                ):
                    location = {
                        "lat": lat,
                        "lon": lon,
                        "label": str(details.get("camera_location_label") or name),
                        "accuracy": str(
                            details.get("camera_location_accuracy")
                            or "recorded location"
                        ),
                    }
            except (KeyError, TypeError, ValueError):
                pass
        if dashboard in CONTEXT_VIEWS:
            group = next(
                label
                for label, members in CONTEXT_VIEWS[dashboard].items()
                if name in members
            )
        elif dashboard == "security":
            group = (
                "Approaches"
                if name in VIEWER_CONFIG.get("security_approaches", [])
                else "Around the home"
            )
        else:
            group = next(
                (
                    s.title()
                    for s in VIEWER_CONFIG.get(
                        "dashboard_group_order", ["plants", "weather"]
                    )
                    if s in groups
                ),
                "Other views",
            )
        cameras.append(
            {
                "name": name,
                "group": group,
                "captured": _saved_capture_time(
                    name, str(details.get("last_screenshot_time") or "")
                ),
                "issue": issue,
                "freshness": source_freshness(name, details),
                "motion_at": str(details.get("last_motion_time") or ""),
                "buffer_enabled": str(details.get("event_buffer_enabled") or "").lower()
                in {"1", "true", "yes", "on"},
                "media_kind": guess_kind(
                    str(resolve_live_stream_url(details) or details.get("url") or "")
                ),
                "caption_at": str(details.get("last_caption_time") or ""),
                "caption": str(details.get("last_caption") or "").split("\t")[0][:220],
                "image": f"/clean_screenshot/{quote(name, safe='')}",
                "live": f"/live?camera={quote(name, safe='')}",
                "location": location,
            }
        )
    cameras.sort(key=lambda c: (bool(c["issue"]), c["group"], c["name"].lower()))
    health_summary = {
        "total": len(cameras),
        "failed": sum(c["issue"] == "capture_failed" for c in cameras),
        "overdue": sum(
            c["issue"] in {"overdue_capture", "awaiting_capture"} for c in cameras
        ),
        "source": sum(
            bool(
                c["freshness"]["older"]
                or c["freshness"]["retained"]
                or c["freshness"]["unchanged_since"]
                or c["freshness"]["clock_ahead"]
            )
            for c in cameras
        ),
        "blocked": sum(
            c["issue"] in {"captcha_deferred", "unusable_page"} for c in cameras
        ),
    }
    if dashboard == "health":
        cameras = [
            c
            for c in cameras
            if c["issue"]
            or c["freshness"]["older"]
            or c["freshness"]["retained"]
            or c["freshness"]["unchanged_since"]
            or c["freshness"]["clock_ahead"]
        ]
    return {
        "health_summary": health_summary,
        "cameras": cameras,
        "healthy": sum(not c["issue"] for c in cameras),
        "mapped": sum(c["location"] is not None for c in cameras),
        "attention": sum(
            bool(
                c["issue"]
                or c["freshness"]["older"]
                or c["freshness"]["retained"]
                or c["freshness"]["unchanged_since"]
                or c["freshness"]["clock_ahead"]
            )
            for c in cameras
        ),
        "dashboard": dashboard,
        "preferred_area": next(
            (
                c["group"]
                for c in cameras
                if c["group"] == VIEWER_CONFIG.get("preferred_areas", {}).get(dashboard)
            ),
            "",
        ),
        "description": CONTEXT_DESCRIPTIONS.get(dashboard, ""),
    }
