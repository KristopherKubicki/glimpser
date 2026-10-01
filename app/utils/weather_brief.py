"""Build a local weather brief from existing Eyebat templates."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import DATABASE_PATH

WEATHER_BRIEF_DIR = Path(
    os.getenv(
        "GLIMPSER_WEATHER_BRIEF_DIR",
        str(Path(DATABASE_PATH).resolve().parent / "weather"),
    )
)
WEATHER_BRIEF_JSON = WEATHER_BRIEF_DIR / "daily_brief.json"
WEATHER_BRIEF_HTML = WEATHER_BRIEF_DIR / "daily_brief.html"
WEATHER_BRIEF_MAX_AGE = timedelta(hours=6)
WEATHER_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

WEATHER_GROUPS = {
    "airport",
    "aviation",
    "beach",
    "beachhouse",
    "buoy",
    "chicago",
    "cosmic",
    "flights",
    "geoelectric",
    "geomagnetic",
    "greatlakes",
    "harbor",
    "kenosha",
    "lake",
    "lakecounty",
    "lakefront",
    "lakemichigan",
    "lightning",
    "lincolnwood",
    "marine",
    "map",
    "milwaukee",
    "noaa",
    "power",
    "powergrid",
    "radar",
    "regional",
    "river",
    "sky",
    "skyline",
    "spaceweather",
    "storm",
    "traffic",
    "usa",
    "usgs",
    "water",
    "weather",
}

WEATHER_NAME_TERMS = {
    "aqi",
    "aviation",
    "buoy",
    "dopler",
    "geoelectric",
    "geomagnetic",
    "groundwater",
    "lightning",
    "noaa",
    "radar",
    "storm",
    "weather",
    "wind",
    "zoomearth",
}

RISK_TERMS = {
    "advisory",
    "alert",
    "delay",
    "flood",
    "fog",
    "hail",
    "hazard",
    "ice",
    "lightning",
    "outage",
    "rain",
    "risk",
    "snow",
    "storm",
    "thunder",
    "tornado",
    "warning",
    "watch",
    "wind",
}

LANE_CONFIG: tuple[dict[str, Any], ...] = (
    {
        "key": "now",
        "title": "Nowcast",
        "purpose": "Radar, warnings, storms, lightning, wind, and fast-moving evidence.",
        "groups": {"radar", "storm", "lightning", "map"},
        "names": {
            "weather",
            "noaa",
            "dopler",
            "codradar",
            "lightning",
            "storms",
            "wind",
            "zoomearth",
        },
        "limit": 8,
    },
    {
        "key": "sky",
        "title": "Sky And Ground Truth",
        "purpose": "Local and regional cameras that show what the air actually looks like.",
        "groups": {
            "sky",
            "skyline",
            "regional",
            "chicago",
            "lincolnwood",
            "milwaukee",
        },
        "names": set(),
        "limit": 10,
    },
    {
        "key": "lake",
        "title": "Lake And Marine",
        "purpose": "Lake Michigan, beach house, harbors, buoys, and shoreline context.",
        "groups": {
            "lake",
            "lakemichigan",
            "greatlakes",
            "marine",
            "harbor",
            "buoy",
            "beach",
            "beachhouse",
        },
        "names": set(),
        "limit": 8,
    },
    {
        "key": "infrastructure",
        "title": "Infrastructure Risk",
        "purpose": "Aviation, roads, power, water, geoelectric, and other weather-sensitive systems.",
        "groups": {
            "airport",
            "flights",
            "traffic",
            "power",
            "powergrid",
            "geoelectric",
            "geomagnetic",
            "water",
            "river",
        },
        "names": {"faa", "aviationweather", "geomagnetic", "geoelectricuscanada1d"},
        "limit": 8,
    },
)


def parse_weather_time(value: Any) -> datetime | None:
    """Parse the timestamp format used in template records."""

    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, WEATHER_TIME_FORMAT)
    except ValueError:
        return None


def split_groups(details: dict[str, Any] | None) -> set[str]:
    """Return normalized groups from a template details dictionary."""

    groups = str((details or {}).get("groups") or "")
    return {group.strip().lower() for group in groups.split(",") if group.strip()}


def _is_weather_template(name: str, details: dict[str, Any]) -> bool:
    groups = split_groups(details)
    lowered_name = name.lower()
    if groups.intersection(WEATHER_GROUPS):
        return True
    return any(term in lowered_name for term in WEATHER_NAME_TERMS)


def _freshness_score(age_minutes: float | None, status: str) -> int:
    if status == "failed":
        return -90
    if age_minutes is None:
        return -35
    if age_minutes <= 30:
        return 80
    if age_minutes <= 120:
        return 55
    if age_minutes <= 360:
        return 28
    if age_minutes <= 1440:
        return 8
    return -30


def _evidence_excerpt(details: dict[str, Any]) -> str:
    caption = str(details.get("last_caption") or "").strip()
    if caption:
        return caption[:240]
    notes = str(details.get("notes") or "").strip()
    if not notes:
        return ""
    return notes.split(". ")[0][:240]


def _risk_score(tile: dict[str, Any]) -> int:
    text = f"{tile.get('name', '')} {tile.get('caption', '')}".lower()
    return sum(1 for term in RISK_TERMS if term in text)


def _tile_score(name: str, details: dict[str, Any], now: datetime) -> tuple[int, float]:
    last_shot = parse_weather_time(details.get("last_screenshot_time"))
    age_minutes = None
    if last_shot:
        age_minutes = max(0.0, (now - last_shot).total_seconds() / 60)
    status = str(details.get("last_capture_status") or "").strip().lower()
    score = _freshness_score(age_minutes, status)
    groups = split_groups(details)
    if {"radar", "weather", "lightning", "storm"}.intersection(groups):
        score += 34
    if {"sky", "skyline", "lakefront", "harbor", "buoy"}.intersection(groups):
        score += 20
    if {"geoelectric", "geomagnetic", "powergrid"}.intersection(groups):
        score += 12
    lowered = name.lower()
    if lowered in {"weather", "noaa", "dopler", "codradar", "lightning", "storms"}:
        score += 46
    if "archive" in groups or "source-stale" in groups:
        score -= 80
    return score, age_minutes if age_minutes is not None else 1_000_000.0


def _build_tile(name: str, details: dict[str, Any], now: datetime) -> dict[str, Any]:
    score, sort_age = _tile_score(name, details, now)
    last_shot = parse_weather_time(details.get("last_screenshot_time"))
    age_minutes = None
    if last_shot:
        age_minutes = max(0, int((now - last_shot).total_seconds() // 60))
    status = str(details.get("last_capture_status") or "").strip() or "unknown"
    tile = {
        "name": name,
        "groups": sorted(split_groups(details)),
        "caption": _evidence_excerpt(details),
        "image_url": f"/last_screenshot/{quote(name)}",
        "last_screenshot_time": str(details.get("last_screenshot_time") or ""),
        "age_minutes": age_minutes,
        "age_label": "unknown" if age_minutes is None else f"{age_minutes}m",
        "status": status,
        "url": str(details.get("url") or ""),
        "score": score,
        "sort_age": sort_age,
    }
    tile["risk_score"] = _risk_score(tile)
    return tile


def _lane_matches(tile: dict[str, Any], lane: dict[str, Any]) -> bool:
    groups = set(tile.get("groups") or [])
    name = str(tile.get("name") or "").lower()
    if groups.intersection(lane["groups"]):
        return True
    return name in lane["names"]


def _headline(
    fresh_count: int, stale_count: int, risk_tiles: list[dict[str, Any]]
) -> str:
    if risk_tiles:
        names = ", ".join(tile["name"] for tile in risk_tiles[:3])
        return f"Weather watch: {names} show the strongest current signal."
    if fresh_count >= 8:
        return "Local weather evidence is current and broadly nominal."
    if stale_count > fresh_count:
        return "Weather sheet is partially stale; verify radar before relying on it."
    return "Local weather sheet is available, but evidence coverage is thin."


def build_weather_brief(
    templates: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a NOAA-like local weather sheet from template metadata."""

    generated_at = now or datetime.utcnow()
    tiles = [
        _build_tile(name, details, generated_at)
        for name, details in templates.items()
        if _is_weather_template(name, details)
    ]
    tiles.sort(
        key=lambda tile: (tile["score"], -tile["sort_age"], tile["name"]), reverse=True
    )

    fresh_tiles = [tile for tile in tiles if tile["status"] in {"fresh", "stale_ok"}]
    stale_tiles = [
        tile
        for tile in tiles
        if tile["status"] not in {"fresh", "stale_ok"} or tile["age_minutes"] is None
    ]
    risk_tiles = sorted(
        [tile for tile in fresh_tiles if tile["risk_score"] > 0],
        key=lambda tile: (tile["risk_score"], tile["score"]),
        reverse=True,
    )

    used_names: set[str] = set()
    sections = []
    for lane in LANE_CONFIG:
        lane_tiles = [
            tile
            for tile in tiles
            if tile["name"] not in used_names and _lane_matches(tile, lane)
        ][: lane["limit"]]
        used_names.update(tile["name"] for tile in lane_tiles)
        sections.append(
            {
                "key": lane["key"],
                "title": lane["title"],
                "purpose": lane["purpose"],
                "tiles": lane_tiles,
            }
        )

    watch_items = [
        {
            "name": tile["name"],
            "caption": tile["caption"]
            or "Current frame has a risk keyword in source metadata.",
            "status": tile["status"],
        }
        for tile in risk_tiles[:6]
    ]
    if not watch_items:
        watch_items = [
            {
                "name": "Normal monitoring",
                "caption": "No strong risk keywords detected in current weather evidence.",
                "status": "nominal",
            }
        ]

    return {
        "generated_at": generated_at.strftime(WEATHER_TIME_FORMAT),
        "generated_at_display": generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "headline": _headline(len(fresh_tiles), len(stale_tiles), risk_tiles),
        "summary": {
            "fresh_sources": len(fresh_tiles),
            "stale_or_failed_sources": len(stale_tiles),
            "total_weather_sources": len(tiles),
            "risk_signals": len(risk_tiles),
        },
        "watch_items": watch_items,
        "sections": sections,
        "top_tiles": tiles[:16],
    }


def _brief_to_html(brief: dict[str, Any]) -> str:
    parts = [
        "<article class='weather-brief-artifact'>",
        f"<h1>{html.escape(str(brief.get('headline') or 'Weather Brief'))}</h1>",
        f"<p>Generated {html.escape(str(brief.get('generated_at_display') or ''))}</p>",
        "<ul>",
    ]
    for item in brief.get("watch_items") or []:
        parts.append(
            "<li>"
            f"<strong>{html.escape(str(item.get('name') or ''))}</strong>: "
            f"{html.escape(str(item.get('caption') or ''))}"
            "</li>"
        )
    parts.extend(["</ul>", "</article>"])
    return "\n".join(parts)


def write_weather_brief(brief: dict[str, Any]) -> None:
    """Persist the generated brief as JSON and a small HTML artifact."""

    WEATHER_BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    WEATHER_BRIEF_JSON.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    WEATHER_BRIEF_HTML.write_text(_brief_to_html(brief) + "\n", encoding="utf-8")


def generate_weather_brief_artifacts(
    templates: dict[str, dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate and persist the daily weather brief artifacts."""

    if templates is None:
        from app.utils.template_manager import get_templates

        templates = get_templates()
    brief = build_weather_brief(templates, now=now)
    write_weather_brief(brief)
    return brief


def load_weather_brief() -> dict[str, Any] | None:
    """Load the persisted weather brief if it exists and is valid JSON."""

    try:
        return json.loads(WEATHER_BRIEF_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_or_generate_weather_brief(
    templates: dict[str, dict[str, Any]],
    *,
    max_age: timedelta = WEATHER_BRIEF_MAX_AGE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a fresh enough brief, regenerating from current templates when stale."""

    current_time = now or datetime.utcnow()
    brief = load_weather_brief()
    generated_at = parse_weather_time((brief or {}).get("generated_at"))
    if brief and generated_at and current_time - generated_at <= max_age:
        return brief
    brief = build_weather_brief(templates, now=current_time)
    write_weather_brief(brief)
    return brief
