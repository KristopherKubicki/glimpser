"""Viewer-safe inventory projections and curated, non-mutating dashboard views."""

from app.viewer_config import load_viewer_config

VIEWER_CONFIG = load_viewer_config()
# Installation aliases augment the generic exclusions; never replace them.
ARCHIVE_GROUPS = frozenset({"archive", "source-stale"}) | frozenset(
    VIEWER_CONFIG.get("archived_groups", [])
)

VIEWER_FIELDS = frozenset(
    {
        "name",
        "groups",
        "frequency",
        "last_screenshot_time",
        "last_caption_time",
        "last_video_time",
        "next_screenshot_time",
        "last_caption",
        "capture_failed",
        "source_template",
        "private_camera",
    }
)
DASHBOARDS = {
    "arrivals": "Arrivals & Departures",
    "property": "Water & Property Health",
    "beach-conditions": "Beach Conditions",
    "security": "Home Security",
    "systems": "Home Systems",
    "growers": "Growers",
    "regional": "Regional / Lake",
    "operations": "Operations",
    "health": "Feed Health",
}
# Explicit membership keeps private property cameras separate from regional views.
CONTEXT_VIEWS = {
    key: VIEWER_CONFIG.get("context_views", {}).get(key, {})
    for key in ("arrivals", "property", "beach-conditions")
}
CONTEXT_DESCRIPTIONS = {
    "arrivals": "Door, driveway and approach views alongside household presence. Presence and camera observations have separate timestamps; a parked car alone does not establish who is home.",
    "property": "Water, power, climate and drainage views. Hub reports and camera images have independent ages. A powered sump pump is not proof that it is pumping or that the basement is dry.",
    "beach-conditions": "Compare the property, nearby lake conditions and approach roads. These are separate locations and capture times, not a synchronized panorama or a forecast for the house.",
}

# Presentation holds are private review decisions; capture jobs stay intact.
ROTATION_REVIEW_HOLDS = VIEWER_CONFIG.get("rotation_review_holds", {})
QUARANTINED_PRESENTATION = frozenset(
    VIEWER_CONFIG.get("quarantined_cameras", []) + list(ROTATION_REVIEW_HOLDS)
)


def viewer_template(name: str, template: dict) -> dict:
    """Omit connection/configuration fields rather than trying to redact secrets."""
    result = {key: value for key, value in template.items() if key in VIEWER_FIELDS}
    result["name"] = name
    return result


def dashboard_matches(dashboard: str, name: str, template: dict) -> bool:
    """Select a saved view without modifying tags, camera settings, or capture jobs."""
    groups = {g.strip().lower() for g in str(template.get("groups") or "").split(",")}
    if dashboard in CONTEXT_VIEWS:
        return "archive" not in groups and any(
            name in members for members in CONTEXT_VIEWS[dashboard].values()
        )
    if dashboard == "health":
        return "archive" not in groups
    if dashboard == "security":
        return "archive" not in groups and (
            name in VIEWER_CONFIG.get("security_cameras", [])
            or bool(groups & set(VIEWER_CONFIG.get("security_groups", ["security"])))
        )
    if dashboard == "systems":
        return (
            "archive" not in groups
            and bool(groups & set(VIEWER_CONFIG.get("systems_groups", ["systems"])))
            and (
                any(
                    name.startswith(prefix)
                    for prefix in VIEWER_CONFIG.get("systems_prefixes", ["Hubitat"])
                )
                or name in VIEWER_CONFIG.get("systems_cameras", [])
            )
        )
    if dashboard == "growers":
        return bool(groups & {"plants", "grower", "cloner"}) and "archive" not in groups
    if dashboard == "regional":
        return bool(
            groups & set(VIEWER_CONFIG.get("regional_groups", ["regional", "weather"]))
        ) and not (
            groups
            & ({"private", "archive"} | set(VIEWER_CONFIG.get("private_groups", [])))
            or template.get("private_camera")
            or name in QUARANTINED_PRESENTATION
        )
    if dashboard == "operations":
        return (
            bool(
                template.get("capture_failed")
                or groups & {"source-stale", "capture-throttled", "source-broken"}
            )
            and "archive" not in groups
        )
    return not dashboard
