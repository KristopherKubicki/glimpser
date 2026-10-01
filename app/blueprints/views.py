from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from flask import Blueprint, jsonify, request, send_from_directory
from PIL import Image

from app.config import SCREENSHOT_DIRECTORY
from app.landing_config import load_landing_config
from app.utils.feed_health import landing_feed_issue
from app.utils.seiche_brief import (
    build_beach_camera_tiles,
    load_or_generate_seiche_brief,
)
from app.utils.source_freshness import source_freshness
from app.utils.visual_dashboard import build_visual_dashboard
from app.utils.weather_brief import load_or_generate_weather_brief
from app.viewer_policy import DASHBOARDS, QUARANTINED_PRESENTATION, VIEWER_CONFIG

LANDING_CONFIG = load_landing_config()

DEFAULT_LANDING_MODE = "medium"
DEFAULT_LANDING_PROFILE = "public"
LANDING_MAX_SCREENSHOT_LAG = timedelta(hours=36)
LANDING_MAX_CONTENT_LAG = timedelta(days=14)
LANDING_OFFLINE_GRACE = timedelta(minutes=10)
LANDING_PORTRAIT_HERO_RATIO_MAX = 0.92
LANDING_RECENT_MOTION_BOOSTS: tuple[tuple[timedelta, int], ...] = (
    (timedelta(minutes=10), 260),
    (timedelta(hours=1), 180),
    (timedelta(hours=6), 120),
    (timedelta(hours=24), 60),
)
LANDING_RECENT_ACTIVITY_BOOSTS: tuple[tuple[timedelta, int], ...] = (
    (timedelta(minutes=15), 100),
    (timedelta(hours=1), 70),
    (timedelta(hours=6), 40),
)
LANDING_GROUP_BONUSES = LANDING_CONFIG["LANDING_GROUP_BONUSES"]
LANDING_GROUP_PENALTIES: dict[str, int] = {
    "cosmic": -70,
    "ecom": -80,
    "health": -24,
    "map": -72,
    "network": -52,
    "news": -18,
    "tv": -16,
}
LANDING_TEXT_PENALTIES: dict[str, int] = {
    "blank": -120,
    "cannot assist": -120,
    "cannot provide assistance": -120,
    "color bars": -120,
    "computer screen": -52,
    "dashboard": -44,
    "error message": -90,
    "graph": -20,
    "grid of buttons": -56,
    "interactive map": -72,
    "loading failure": -140,
    "map tile loading failure": -160,
    "map unavailable": -160,
    "only a footer": -140,
    "old computer screen": -60,
    "screenshot of": -16,
    "television screen": -28,
    "unreadable": -120,
    "warning sign": -18,
    "webpage": -22,
    "website": -18,
}
LANDING_NAME_PENALTIES = LANDING_CONFIG["LANDING_NAME_PENALTIES"]
LANDING_URL_BONUSES: dict[str, int] = {
    "earthcam.com": 18,
    "weatherbug.com": 18,
    "skylinewebcams.com": 18,
    "/picture": 14,
}
LANDING_URL_PENALTIES: dict[str, int] = {
    "aqicn.org": -64,
    "browserleaks": -90,
    "creepjs": -90,
    "fast.com": -96,
    "hubitat": -72,
    "redfin": -80,
    "spacetelescopelive": -50,
    "zoom.earth": -60,
}
LANDING_MODE_PROFILES: dict[str, dict[str, Any]] = {
    "low": {
        "chrome_auto_hide_ms": 2400,
        "default_rhythm_copy": "Low",
        "event_buffer_default": "off",
        "hero_video_enabled": False,
        "hero_video_playback_rate": 0.0,
        "image_refresh_ms": 0,
        "key": "low",
        "label": "Low",
        "max_scenes": 3,
        "pip_video_enabled": False,
        "pip_video_playback_rate": 0.0,
        "rotation_ms": 75000,
        "scene_size": 2,
        "short_label": "Low",
    },
    "medium": {
        "chrome_auto_hide_ms": 2600,
        "default_rhythm_copy": "Slow",
        "event_buffer_default": "off",
        "hero_video_enabled": False,
        "hero_video_playback_rate": 0.0,
        "image_refresh_ms": 300000,
        "key": "medium",
        "label": "Medium",
        "max_scenes": 4,
        "pip_video_enabled": True,
        "pip_video_playback_rate": 0.14,
        "rotation_ms": 40000,
        "scene_size": 4,
        "short_label": "Med",
    },
    "high": {
        "chrome_auto_hide_ms": 2200,
        "default_rhythm_copy": "Steady",
        "event_buffer_default": "auto",
        "hero_video_enabled": True,
        "hero_video_playback_rate": 0.16,
        "image_refresh_ms": 180000,
        "key": "high",
        "label": "High",
        "max_scenes": 5,
        "pip_video_enabled": True,
        "pip_video_playback_rate": 0.2,
        "rotation_ms": 32000,
        "scene_size": 5,
        "short_label": "High",
    },
    "ultra": {
        "chrome_auto_hide_ms": 1800,
        "default_rhythm_copy": "Active",
        "event_buffer_default": "auto",
        "hero_video_enabled": True,
        "hero_video_playback_rate": 0.2,
        "image_refresh_ms": 90000,
        "key": "ultra",
        "label": "Ultra",
        "max_scenes": 6,
        "pip_video_enabled": True,
        "pip_video_playback_rate": 0.26,
        "rotation_ms": 26000,
        "scene_size": 6,
        "short_label": "Ultra",
    },
}
LANDING_CONTENT_PROFILES = LANDING_CONFIG["LANDING_CONTENT_PROFILES"]
LANDING_LANE_HINTS = LANDING_CONFIG["LANDING_LANE_HINTS"]
LANDING_HOST_PROFILE_HINTS = LANDING_CONFIG["LANDING_HOST_PROFILE_HINTS"]
LANDING_HOST_MODE_HINTS = LANDING_CONFIG["LANDING_HOST_MODE_HINTS"]
LANDING_EVENT_RECENT_WINDOWS: tuple[tuple[timedelta, int], ...] = (
    (timedelta(minutes=2), 320),
    (timedelta(minutes=10), 220),
    (timedelta(minutes=30), 140),
)
LANDING_EVENT_INTERRUPT_MS: dict[str, int] = {
    "notice": 12000,
    "alert": 18000,
    "significant": 26000,
}
LANDING_EVENT_POLL_MS: dict[str, int] = {
    "public": 0,
    "kitchen": 20000,
    "living": 5000,
    "office": 5000,
    "hal": 10000,
}
LANDING_PRIORITY_PROFILES = frozenset({"living", "office"})
LANDING_PRIORITY_CAMERAS = LANDING_CONFIG["LANDING_PRIORITY_CAMERAS"]


def _is_priority_camera(name: str, details: dict[str, Any]) -> bool:
    """Use known entrances or an explicit priority group for room interruptions."""
    groups = {g.strip().lower() for g in str(details.get("groups") or "").split(",")}
    return name in LANDING_PRIORITY_CAMERAS or "priority" in groups


LANDING_EVENT_BUFFER_MODES = {"off", "auto", "on"}
LANDING_EVENT_BUFFER_AUTO_EVERY = 3
LANDING_EVENT_BUFFER_EXCLUDE_HINTS = (
    "grower",
    "plant",
    "plants",
)
LANDING_EVENT_BUFFER_INCLUDE_HINTS = (
    "landing-buffer",
    "landing_buffer",
)
LANDING_EVENT_BUFFER_DISABLE_HINTS = (
    "no-landing-buffer",
    "no_landing_buffer",
)

LANDING_PROFILE_EXCLUDED_CAMERAS = LANDING_CONFIG["LANDING_PROFILE_EXCLUDED_CAMERAS"]


def _first_group(details: dict[str, Any]) -> str:
    groups = [
        token.strip()
        for token in str(details.get("groups", "")).split(",")
        if token.strip()
    ]
    return groups[0] if groups else "highlights"


def _group_label(group_name: str) -> str:
    return str(group_name or "highlights").replace("_", " ").title()


def _landing_mode_profile(
    mode_name: str | None,
    host_name: str | None = None,
) -> dict[str, Any]:
    explicit = str(mode_name or "").strip().lower()
    if explicit:
        return LANDING_MODE_PROFILES.get(
            explicit,
            LANDING_MODE_PROFILES[DEFAULT_LANDING_MODE],
        )

    lower_host = str(host_name or "").strip().lower()
    for host_hint, mode_key in LANDING_HOST_MODE_HINTS:
        if lower_host == host_hint or lower_host.split(".", 1)[0] == host_hint:
            return LANDING_MODE_PROFILES[mode_key]

    return LANDING_MODE_PROFILES[DEFAULT_LANDING_MODE]


def _landing_content_profile(
    profile_name: str | None,
    host_name: str | None = None,
) -> dict[str, Any]:
    explicit = str(profile_name or "").strip().lower()
    if explicit:
        return LANDING_CONTENT_PROFILES.get(
            explicit,
            LANDING_CONTENT_PROFILES[DEFAULT_LANDING_PROFILE],
        )

    lower_host = str(host_name or "").strip().lower()
    for host_hint, profile_key in LANDING_HOST_PROFILE_HINTS:
        if lower_host == host_hint or lower_host.split(".", 1)[0] == host_hint:
            return LANDING_CONTENT_PROFILES[profile_key]

    return LANDING_CONTENT_PROFILES[DEFAULT_LANDING_PROFILE]


def _landing_event_buffer_mode(
    mode_name: str | None,
    mode_profile: dict[str, Any],
) -> str:
    explicit = str(mode_name or "").strip().lower()
    aliases = {
        "1": "on",
        "true": "on",
        "yes": "on",
        "gif": "on",
        "motion": "on",
        "0": "off",
        "false": "off",
        "no": "off",
        "none": "off",
    }
    explicit = aliases.get(explicit, explicit)
    if explicit in LANDING_EVENT_BUFFER_MODES:
        return explicit

    fallback = str(mode_profile.get("event_buffer_default") or "off").lower()
    return fallback if fallback in LANDING_EVENT_BUFFER_MODES else "off"


def _landing_capture_age(value: Any) -> str:
    """Render a useful capture age even before browser modules finish loading."""
    parsed = _parse_landing_timestamp(value)
    if parsed is None:
        return "Awaiting capture"
    seconds = int((datetime.utcnow() - parsed).total_seconds())
    if seconds < -60:
        return "Capture clock ahead"
    if seconds < 10:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    return "just now"


def _landing_caption(details: dict[str, Any]) -> str:
    for key in ("last_caption", "notes"):
        value = str(details.get(key, "")).strip()
        if value:
            return value
    return ""


def _landing_event_poll_ms(profile: dict[str, Any]) -> int:
    return max(0, int(LANDING_EVENT_POLL_MS.get(profile["key"], 0)))


def _parse_landing_timestamp(value: Any) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def _is_local_landing_source(details: dict[str, Any]) -> bool:
    text = " ".join(
        (
            str(details.get("groups") or "").lower(),
            str(details.get("url") or "").lower(),
            str(details.get("name") or "").lower(),
        )
    )
    # Regional north-shore feeds often keep stale caption metadata even when the
    # screenshot itself is current. Treat those local-interest sources like the
    # rest of the trusted local lanes so they are not suppressed unnecessarily.
    return any(token in text for token in LANDING_CONFIG["LANDING_LOCAL_HINTS"])


def _landing_recency_boost(
    value: Any,
    reference_time: datetime | None,
    windows: tuple[tuple[timedelta, int], ...],
) -> int:
    if reference_time is None:
        return 0

    parsed = _parse_landing_timestamp(value)
    if parsed is None:
        return 0

    age = reference_time - parsed
    if age < timedelta(0):
        age = timedelta(0)

    for max_age, boost in windows:
        if age <= max_age:
            return boost

    return 0


@lru_cache(maxsize=512)
def _landing_media_size(
    name: str,
    last_screenshot_time: str,
) -> tuple[int, int] | None:
    camera_dir = Path(SCREENSHOT_DIRECTORY) / name
    if not camera_dir.is_dir():
        return None

    latest_file: Path | None = None
    latest_mtime = -1.0
    for path in camera_dir.iterdir():
        if path.name.startswith(".") or path.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:
            continue

        try:
            stat_result = path.stat()
        except FileNotFoundError:
            continue
        if not path.is_file():
            continue
        if stat_result.st_mtime > latest_mtime:
            latest_file = path
            latest_mtime = stat_result.st_mtime

    if latest_file is None:
        return None

    try:
        with Image.open(latest_file) as image:
            return image.size
    except (FileNotFoundError, OSError):
        return None


def _is_portrait_landing_media(name: str, details: dict[str, Any]) -> bool:
    size = _landing_media_size(name, str(details.get("last_screenshot_time") or ""))
    if size:
        width, height = size
        if width > 0 and height > 0:
            return width / height < LANDING_PORTRAIT_HERO_RATIO_MAX

    return int(details.get("rotation") or 0) in {-90, 90}


def _landing_lanes(name: str, details: dict[str, Any]) -> tuple[str, ...]:
    combined_text = " ".join(
        (
            name.strip().lower(),
            _landing_caption(details).lower(),
            str(details.get("url") or "").lower(),
            str(details.get("groups") or "").lower(),
        )
    )
    lanes = {
        lane
        for lane, hints in LANDING_LANE_HINTS.items()
        if _contains_any(combined_text, hints)
    }
    if not lanes:
        lanes.add("scenic")
    return tuple(sorted(lanes))


def _landing_quality_score(name: str, details: dict[str, Any]) -> int:
    groups = {
        token.strip().lower()
        for token in str(details.get("groups", "")).split(",")
        if token.strip()
    }
    score = 0
    for token in groups:
        score += LANDING_GROUP_BONUSES.get(token, 0)
        score += LANDING_GROUP_PENALTIES.get(token, 0)

    lower_name = name.strip().lower()
    lower_caption = _landing_caption(details).lower()
    lower_url = str(details.get("url") or "").lower()
    combined_text = " ".join((lower_name, lower_caption, lower_url))

    for token, weight in LANDING_NAME_PENALTIES.items():
        if token in lower_name:
            score += weight
    for token, weight in LANDING_TEXT_PENALTIES.items():
        if token in combined_text:
            score += weight
    for token, weight in LANDING_URL_BONUSES.items():
        if token in lower_url:
            score += weight
    for token, weight in LANDING_URL_PENALTIES.items():
        if token in lower_url:
            score += weight
    return score


def _landing_profile_score(
    name: str,
    details: dict[str, Any],
    profile: dict[str, Any],
) -> int:
    score = _landing_quality_score(name, details)
    for lane in _landing_lanes(name, details):
        score += int(profile["lane_bias"].get(lane, 0))
    return score


def _landing_event_score(
    details: dict[str, Any],
    lanes: tuple[str, ...],
    profile: dict[str, Any],
    reference_time: datetime | None,
) -> int:
    if profile["key"] == "public" and {"home", "ops"} & set(lanes):
        return 0

    motion_boost = _landing_recency_boost(
        details.get("last_motion_time"),
        reference_time,
        LANDING_RECENT_MOTION_BOOSTS,
    )
    if motion_boost:
        motion_multiplier = 1.0
        if "home" in lanes:
            motion_multiplier += 0.4
        if "ops" in lanes:
            motion_multiplier += 0.2
        if profile["key"] == "hal":
            motion_multiplier += 0.35
        elif profile["key"] == "office":
            motion_multiplier += 0.15
        motion_boost = int(motion_boost * motion_multiplier)

    activity_boost = 0
    if {"ops", "world", "science"} & set(lanes):
        activity_boost = max(
            _landing_recency_boost(
                details.get("last_caption_time"),
                reference_time,
                LANDING_RECENT_ACTIVITY_BOOSTS,
            ),
            _landing_recency_boost(
                details.get("last_video_time"),
                reference_time,
                LANDING_RECENT_ACTIVITY_BOOSTS,
            ),
        )
        if activity_boost and profile["key"] == "hal":
            activity_boost = int(activity_boost * 1.2)

    return motion_boost + activity_boost


def _landing_item(
    name: str,
    details: dict[str, Any],
    profile: dict[str, Any],
    reference_time: datetime | None = None,
    event_buffer_mode: str = "off",
) -> dict[str, Any]:
    group_name = _first_group(details)
    group_url = "/" if group_name == "highlights" else f"/group/{quote(group_name)}"
    lanes = _landing_lanes(name, details)
    is_portrait_media = _is_portrait_landing_media(name, details)
    profile_score = _landing_profile_score(name, details, profile)
    event_score = _landing_event_score(details, lanes, profile, reference_time)
    hero_score = profile_score - (120 if is_portrait_media else 0)
    return {
        "caption": _landing_caption(details).split("\t")[0],
        "caption_at": str(details.get("last_caption_time") or ""),
        "capture_age": _landing_capture_age(details.get("last_screenshot_time")),
        "freshness": source_freshness(name, details),
        "event_score": event_score,
        "event_buffer_url": _landing_event_buffer_url(
            name,
            details,
            event_buffer_mode,
        ),
        "group_label": _group_label(group_name),
        "group_name": group_name,
        "group_url": group_url,
        "image_url": f"/clean_screenshot/{quote(name)}",
        "is_portrait_media": is_portrait_media,
        "lanes": lanes,
        "last_motion_time": str(details.get("last_motion_time") or ""),
        "priority_event": _is_priority_camera(name, details),
        "replay_available": _is_landing_event_buffer_enabled(
            details.get("event_buffer_enabled")
        ),
        "last_screenshot_time": str(details.get("last_screenshot_time") or ""),
        "last_video_time": str(details.get("last_video_time") or ""),
        "live_url": f"/live?camera={quote(name)}",
        "name": name,
        "quality_score": _landing_quality_score(name, details),
        "profile_score": profile_score,
        # Keep portrait wall cams in the lane, but let wide scenic/home shots
        # win the hero slot when both are available.
        "hero_score": hero_score,
        "scene_score": hero_score + event_score,
        "video_url": f"/last_video/{quote(name)}",
    }


def _landing_score_threshold(
    name: str,
    details: dict[str, Any],
    profile: dict[str, Any],
) -> int:
    lanes = _landing_lanes(name, details)
    if "ops" in lanes and profile["key"] == "office":
        return -140
    if "science" in lanes and profile["key"] in {"living", "office"}:
        return -80
    if "home" in lanes and profile["key"] in {"kitchen", "living", "office"}:
        return -80
    return -20


def _is_landing_event_buffer_enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _landing_event_buffer_url(
    name: str,
    details: dict[str, Any],
    event_buffer_mode: str,
) -> str:
    if event_buffer_mode == "off":
        return ""
    if not _is_landing_event_buffer_enabled(details.get("event_buffer_enabled")):
        return ""

    searchable_text = " ".join(
        str(details.get(key) or "")
        for key in ("groups", "notes", "prompt", "last_caption")
    ).lower()
    normalized_name = str(name or "").lower()
    text = f"{normalized_name} {searchable_text}"
    if _contains_any(text, LANDING_EVENT_BUFFER_DISABLE_HINTS):
        return ""
    if _contains_any(text, LANDING_EVENT_BUFFER_EXCLUDE_HINTS) and not _contains_any(
        text,
        LANDING_EVENT_BUFFER_INCLUDE_HINTS,
    ):
        return ""

    return f"/event_buffer/{quote(name)}.gif"


def _is_landing_fresh_enough(
    details: dict[str, Any],
    freshest_screenshot_time: datetime | None,
) -> bool:
    last_screenshot_time = _parse_landing_timestamp(details.get("last_screenshot_time"))
    if not last_screenshot_time:
        return False
    if not freshest_screenshot_time:
        return True
    return freshest_screenshot_time - last_screenshot_time <= LANDING_MAX_SCREENSHOT_LAG


def _has_stale_landing_content(details: dict[str, Any]) -> bool:
    if _is_local_landing_source(details):
        return False

    last_screenshot_time = _parse_landing_timestamp(details.get("last_screenshot_time"))
    last_caption_time = _parse_landing_timestamp(details.get("last_caption_time"))
    if not last_screenshot_time or not last_caption_time:
        return False
    # Some upstream still-image sources keep serving an old frozen frame while
    # Glimpser continues to capture it on schedule. When the capture timestamp
    # is current but the caption timestamp trails by weeks, keep that scene off
    # the landing page until the content actually changes again.
    return last_screenshot_time - last_caption_time > LANDING_MAX_CONTENT_LAG


def _is_landing_candidate(
    details: dict[str, Any],
    profile: dict[str, Any],
    freshest_screenshot_time: datetime | None = None,
) -> bool:
    name = str(details.get("name") or "")
    if name in LANDING_PROFILE_EXCLUDED_CAMERAS.get(profile["key"], frozenset()):
        return False

    score = _landing_profile_score(name, details, profile)
    last_screenshot_time = str(details.get("last_screenshot_time") or "").strip()
    last_screenshot_dt = _parse_landing_timestamp(last_screenshot_time)
    offline_since = str(details.get("offline_since") or "").strip()
    offline_since_dt = _parse_landing_timestamp(offline_since)

    # Some templates keep stale offline metadata even after a later successful
    # capture. For the landing page, trust a fresh screenshot unless the
    # offline marker stays newer by more than a short grace window. A few
    # seconds or minutes of skew is common while metadata settles.
    is_still_offline = bool(
        last_screenshot_dt
        and offline_since_dt
        and offline_since_dt - last_screenshot_dt > LANDING_OFFLINE_GRACE
    )
    return bool(
        last_screenshot_time
        and _is_landing_fresh_enough(details, freshest_screenshot_time)
        and not _has_stale_landing_content(details)
        and not details.get("capture_failed")
        and not is_still_offline
        and (
            profile.get("all_eligible")
            or score > _landing_score_threshold(name, details, profile)
        )
    )


def _is_landing_fallback_candidate(
    details: dict[str, Any],
    freshest_screenshot_time: datetime | None = None,
) -> bool:
    return _is_landing_fresh_enough(details, freshest_screenshot_time) and not (
        _has_stale_landing_content(details)
    )


def _scene_lanes(scene: dict[str, Any]) -> tuple[str, ...]:
    return tuple(scene["hero"].get("lanes") or ())


def _scene_group_cap(profile: dict[str, Any], group_name: str) -> int | None:
    caps = profile.get("group_scene_caps") or {}
    value = caps.get(group_name)
    return int(value) if value else None


def _scene_window_size(profile: dict[str, Any], group_name: str, default: int) -> int:
    sizes = profile.get("group_window_sizes") or {}
    value = sizes.get(group_name)
    if value is None:
        return max(1, int(default))
    return max(1, int(value))


def _scene_activity_level(scene: dict[str, Any]) -> str:
    lanes = set(_scene_lanes(scene))
    if {"home", "ops", "world"} & lanes:
        return "active"
    if {"science", "retail", "plants"} & lanes:
        return "steady"
    return "calm"


def _landing_event_level(motion_score: int) -> str | None:
    if motion_score >= 280:
        return "significant"
    if motion_score >= 180:
        return "alert"
    if motion_score > 0:
        return "notice"
    return None


def _scene_motion_event(
    scene: dict[str, Any],
    profile: dict[str, Any],
    reference_time: datetime | None,
) -> dict[str, Any] | None:
    hero = scene.get("hero") or {}
    priority_only = profile["key"] in LANDING_PRIORITY_PROFILES
    if priority_only:
        occurred = _parse_landing_timestamp(hero.get("last_motion_time"))
        captured = _parse_landing_timestamp(hero.get("last_screenshot_time"))
        now = reference_time or datetime.utcnow()
        if not hero.get("priority_event") or not occurred or not captured:
            return None
        if not (0 <= (now - occurred).total_seconds() <= 120):
            return None
        if not (0 <= (now - captured).total_seconds() <= 120):
            return None
    lanes = set(_scene_lanes(scene))
    motion_score = _landing_recency_boost(
        hero.get("last_motion_time"),
        reference_time,
        LANDING_EVENT_RECENT_WINDOWS,
    )
    if motion_score <= 0:
        return None

    if "home" in lanes:
        motion_score = int(motion_score * 1.35)
    if "ops" in lanes:
        motion_score = int(motion_score * 1.15)
    if profile["key"] == "hal":
        motion_score = int(motion_score * 1.1)

    level = _landing_event_level(motion_score)
    if not level:
        return None

    prefer_video = level == "significant" and bool(hero.get("last_video_time"))
    return {
        "camera_name": hero.get("name", ""),
        "interrupt_ms": 26000 if priority_only else LANDING_EVENT_INTERRUPT_MS[level],
        "priority": priority_only,
        "replay_available": bool(hero.get("replay_available")),
        "occurred_at": str(hero.get("last_motion_time") or ""),
        "key": f"{hero.get('name', '')}:{hero.get('last_motion_time', '')}",
        "level": level,
        "motion_score": motion_score,
        "prefer_video": prefer_video,
        "scene_id": scene["id"],
    }


def _build_landing_events(
    scenes: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if _landing_event_poll_ms(profile) <= 0:
        return []

    reference_time = datetime.utcnow()
    events = [
        event
        for event in (
            _scene_motion_event(scene, profile, reference_time) for scene in scenes
        )
        if event is not None
    ]
    return sorted(
        events,
        key=lambda event: (
            event["occurred_at"] if event["priority"] else "",
            event["motion_score"],
            event["camera_name"],
        ),
        reverse=True,
    )[: 10 if profile["key"] in LANDING_PRIORITY_PROFILES else 3]


OFFICE_SCENIC_DWELL_CAMERAS = frozenset(
    {
        "River",
        "UICSkyline",
        "SheboyganBeach",
        "CindysRooftopBean",
        "LincolnPark2800LakeShore",
        "NorthPointMarina",
        "GOES16",
        "SouthHavenSouthBeachGLERL",
        "SouthHavenPierLightGLERL",
        "WaukeganHarborWeatherbug",
        "BotanyPondUChicago",
    }
)


def _office_scene_dwell_ms(scene: dict[str, Any], now: datetime | None = None) -> int:
    """Give fresh, relevant office views enough reading or watching time."""
    hero = scene.get("hero") or {}
    freshness = hero.get("freshness") or {}
    if any(
        freshness.get(flag)
        for flag in (
            "capture_overdue",
            "retained",
            "source_unchanged",
            "older",
            "waiting_for_browser",
            "clock_ahead",
            "low_light",
        )
    ):
        return 0
    now = now or datetime.utcnow()

    def recent(value: Any, seconds: int) -> bool:
        timestamp = _parse_landing_timestamp(value)
        return bool(timestamp and 0 <= (now - timestamp).total_seconds() <= seconds)

    # Capture recency is only a gate, not proof of source freshness. Explicit
    # degraded-source flags above veto the longer hold, including cached frames.
    if not recent(hero.get("last_screenshot_time"), 30 * 60):
        return 0
    name = str(hero.get("name") or "")
    lanes = set(hero.get("lanes") or ())
    if (
        name.lower().startswith(tuple(LANDING_CONFIG["LANDING_STATUS_PREFIXES"]))
        or name in LANDING_CONFIG["LANDING_STATUS_CAMERAS"]
    ):
        return 40000
    relevant_camera = bool(
        {"home", "retail"} & lanes
        or hero.get("priority_event")
        or scene.get("group_name") in LANDING_CONFIG["LANDING_DWELL_GROUPS"]
    )
    scenic_pick = name in OFFICE_SCENIC_DWELL_CAMERAS
    if not (relevant_camera or scenic_pick):
        return 0
    if (
        relevant_camera
        and recent(hero.get("last_screenshot_time"), 10 * 60)
        and recent(hero.get("last_motion_time"), 5 * 60)
    ):
        return 50000
    if recent(hero.get("last_video_time"), 15 * 60):
        return 45000
    return 35000


def _apply_scene_timing(
    scene: dict[str, Any],
    mode_profile: dict[str, Any],
    content_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_rotation_ms = int(mode_profile["rotation_ms"])
    base_hero_rate = float(mode_profile["hero_video_playback_rate"])
    base_pip_rate = float(mode_profile["pip_video_playback_rate"])
    activity_level = _scene_activity_level(scene)
    content = content_profile or {}
    base_rotation_ms = int(content.get("rotation_ms", base_rotation_ms))

    if activity_level == "active":
        rotation_multiplier = 1.0
        playback_multiplier = 1.0
    elif activity_level == "steady":
        rotation_multiplier = 1.25
        playback_multiplier = 0.85
    else:
        rotation_multiplier = 1.6
        playback_multiplier = 0.7

    # Keep configured priority groups visible for longer once they surface in
    # the rundown. This complements the distribution pass so those scenes are
    # both spaced through the loop and given enough dwell to actually read.
    group_rotation_multiplier = float(
        (content.get("group_rotation_multipliers") or {}).get(
            scene.get("group_name"),
            1.0,
        )
    )

    scene["activity_level"] = activity_level
    scene["rotation_ms"] = int(
        base_rotation_ms * rotation_multiplier * group_rotation_multiplier
    )
    if content.get("key") == "office":
        scene["rotation_ms"] = max(
            min(scene["rotation_ms"], 24000), _office_scene_dwell_ms(scene)
        )
    if content.get("max_rotation_ms"):
        scene["rotation_ms"] = min(
            scene["rotation_ms"], int(content["max_rotation_ms"])
        )
    scene["hero_video_playback_rate"] = round(
        base_hero_rate * playback_multiplier,
        2,
    )
    scene["pip_video_playback_rate"] = round(base_pip_rate * playback_multiplier, 2)
    return scene


def _landing_breadth(
    mode_profile: dict[str, Any] | None,
    content_profile: dict[str, Any] | None,
) -> tuple[int, int]:
    """Return ``(scene_size, max_scenes)`` for a landing request."""

    profile = mode_profile or LANDING_MODE_PROFILES[DEFAULT_LANDING_MODE]
    content = content_profile or LANDING_CONTENT_PROFILES[DEFAULT_LANDING_PROFILE]
    scene_size = int(
        content.get(
            "scene_size",
            int(profile["scene_size"]) + int(content.get("scene_size_bonus", 0)),
        )
    )
    max_scenes = int(
        content.get(
            "max_scenes",
            int(profile["max_scenes"]) + int(content.get("max_scenes_bonus", 0)),
        )
    )
    return scene_size, max_scenes


def _group_scene_chunks(
    group_name: str,
    ordered_items: list[dict[str, Any]],
    scene_size: int,
    content: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    if not ordered_items:
        return []

    # Comprehensive room rotations give every healthy camera its own main view.
    if content.get("all_eligible"):
        return [[item] for item in ordered_items]

    window_size = _scene_window_size(
        content,
        group_name,
        int(content.get("scene_window_size", scene_size)),
    )
    stride = max(1, int(content.get("scene_chunk_stride", window_size)))
    max_group_scenes = max(1, int(content.get("max_group_scenes", 1)))
    chunks: list[list[dict[str, Any]]] = []
    start = 0

    # Room profiles use overlapping hero/PiP windows so each eligible camera
    # can lead a scene instead of remaining buried in another camera's related
    # views. Per-group caps still prevent one family from dominating the loop.
    while start < len(ordered_items) and len(chunks) < max_group_scenes:
        chunk = ordered_items[start : start + window_size]
        if not chunk:
            break
        chunks.append(chunk)
        if start + window_size >= len(ordered_items):
            break
        start += stride

    return chunks or [ordered_items[:window_size]]


def _compose_profiled_scenes(
    scenes: list[dict[str, Any]],
    profile: dict[str, Any],
    max_scenes: int,
) -> list[dict[str, Any]]:
    ordered = sorted(
        scenes,
        key=lambda scene: (
            scene.get("scene_score", scene["hero_score"]),
            scene.get("event_score", 0),
            scene["profile_score"],
            scene["hero"]["last_screenshot_time"],
        ),
        reverse=True,
    )
    if not ordered:
        return []

    if profile.get("all_eligible"):
        max_scenes = len(ordered)

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    selected_group_counts: defaultdict[str, int] = defaultdict(int)

    def can_pick(scene: dict[str, Any]) -> bool:
        if scene["id"] in used_ids:
            return False
        group_cap = _scene_group_cap(profile, scene["group_name"])
        if (
            not profile.get("all_eligible")
            and group_cap is not None
            and selected_group_counts[scene["group_name"]] >= group_cap
        ):
            return False
        return True

    def remember(scene: dict[str, Any]) -> None:
        selected.append(scene)
        used_ids.add(scene["id"])
        selected_group_counts[scene["group_name"]] += 1

    def pick_for_group(group_name: str) -> bool:
        for scene in ordered:
            if not can_pick(scene):
                continue
            if scene["group_name"] != group_name:
                continue
            remember(scene)
            return True
        return False

    def pick_for_lane(lane: str) -> bool:
        for scene in ordered:
            if not can_pick(scene):
                continue
            if lane not in _scene_lanes(scene):
                continue
            remember(scene)
            return True
        return False

    def pick_for_camera(camera_name: str) -> bool:
        for scene in ordered:
            if not can_pick(scene):
                continue
            if scene["hero"]["name"] != camera_name:
                continue
            remember(scene)
            return True
        return False

    for camera_name in profile.get("camera_minimums", ()):
        if len(selected) >= max_scenes:
            break
        pick_for_camera(camera_name)

    for group_name in profile.get("group_minimums", ()):
        if len(selected) >= max_scenes:
            break
        pick_for_group(group_name)

    for lane in profile["lane_minimums"]:
        if len(selected) >= max_scenes:
            break
        pick_for_lane(lane)

    while len(selected) < max_scenes:
        added = False
        for lane in profile["lane_fill_order"]:
            if len(selected) >= max_scenes:
                break
            if pick_for_lane(lane):
                added = True
        if not added:
            break

    for scene in ordered:
        if len(selected) >= max_scenes:
            break
        if not can_pick(scene):
            continue
        remember(scene)

    composed = selected[:max_scenes]
    for group_name in profile.get("distributed_groups", ()):
        composed = _distribute_group_scenes(composed, group_name)
    return composed


def _distribute_group_scenes(
    scenes: list[dict[str, Any]], group_name: str
) -> list[dict[str, Any]]:
    """Spread repeated group scenes through the final rundown.

    The configured group was being selected correctly but stacked at the top because camera
    minimums are applied before the broader fill order. This helper preserves
    the same selected scenes while distributing one repeated group across the
    rundown so it stays visible throughout the loop instead of front-loading.
    """

    priority = [scene for scene in scenes if scene["group_name"] == group_name]
    if len(priority) <= 1 or len(priority) == len(scenes):
        return scenes

    others = [scene for scene in scenes if scene["group_name"] != group_name]
    total = len(scenes)
    priority_count = len(priority)
    target_positions: list[int] = []
    previous = -1

    for index in range(priority_count):
        target = 0 if index == 0 else round(index * total / priority_count)
        target = max(previous + 1, target)
        target = min(target, total - (priority_count - index))
        target_positions.append(target)
        previous = target

    target_position_set = set(target_positions)
    priority_iter = iter(priority)
    other_iter = iter(others)
    distributed: list[dict[str, Any]] = []

    for position in range(total):
        if position in target_position_set:
            distributed.append(next(priority_iter))
        else:
            distributed.append(next(other_iter))

    return distributed


def _satellite_landing_scene(
    mode_profile: dict[str, Any], content_profile: dict[str, Any]
) -> dict[str, Any] | None:
    """Offer one current daily satellite frame as a distinct rotation scene."""
    archive = Path("/data/glimpser/satellite/chicago-kenosha")
    frames = sorted(archive.glob("????-??-??.jpg")) if archive.is_dir() else []
    if not frames:
        return None
    frame = frames[-1]
    try:
        data_day = datetime.strptime(frame.stem, "%Y-%m-%d").date()
    except ValueError:
        return None
    if not 0 <= (datetime.now().date() - data_day).days <= 3:
        return None
    image_url = f"/satellite/media/{frame.name}"
    hero = {
        "caption": (
            f"Satellite data day {data_day.isoformat()}. Chicago, Lincolnwood "
            "and the Kenosha shoreline in one frame. Clouds may hide the ground."
        ),
        "caption_at": "",
        "capture_age": data_day.isoformat(),
        "event_buffer_url": "",
        "freshness": {},
        "group_label": "Regional satellite",
        "group_name": "regional",
        "group_url": "/satellite",
        "image_url": image_url,
        "is_portrait_media": True,
        "lanes": ("regional", "scenic"),
        "last_motion_time": "",
        "last_screenshot_time": "",
        "last_video_time": "",
        "live_url": "/satellite",
        "name": "Chicago to the Beach · satellite",
        "priority_event": False,
        "replay_available": False,
        "video_url": "",
    }
    scene = {
        "event_score": 0,
        "group_label": "Regional satellite",
        "group_name": "regional",
        "hero": hero,
        "hero_score": 0,
        "id": "satellite-chicago-beach",
        "pip": None,
        "profile_score": 0,
        "quality_score": 0,
        "related": [],
        "rhythm_copy": mode_profile["default_rhythm_copy"],
        "scene_score": 0,
        "theme_copy": "Daily satellite · Chicago to the Beach",
    }
    return _apply_scene_timing(scene, mode_profile, content_profile)


def _build_landing_scenes(
    templates: dict[str, dict[str, Any]],
    mode_profile: dict[str, Any] | None = None,
    content_profile: dict[str, Any] | None = None,
    event_buffer_mode: str = "off",
) -> list[dict[str, Any]]:
    """Build a small, fresh scene list for the lightweight landing page."""

    profile = mode_profile or LANDING_MODE_PROFILES[DEFAULT_LANDING_MODE]
    content = content_profile or LANDING_CONTENT_PROFILES[DEFAULT_LANDING_PROFILE]
    scene_size, max_scenes = _landing_breadth(profile, content)
    freshest_screenshot_time = max(
        (
            parsed
            for parsed in (
                _parse_landing_timestamp(details.get("last_screenshot_time"))
                for details in templates.values()
            )
            if parsed is not None
        ),
        default=None,
    )
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    fallback_items: list[dict[str, str]] = []

    for name, details in templates.items():
        # Keep inventory-only feeds available in the template catalog, but do
        # not let them enter the public kiosk rotations.
        if details.get("private_camera") or name in QUARANTINED_PRESENTATION:
            continue
        groups = {
            g.strip().lower() for g in str(details.get("groups") or "").split(",")
        }
        # Expanding room pools must not revive intentionally retired monitors.
        if "archive" in groups:
            continue
        if content["key"] == "public" and "private" in groups:
            continue
        if content["key"] in LANDING_PRIORITY_PROFILES and landing_feed_issue(details):
            continue
        item_details = dict(details)
        item_details["name"] = name
        item = _landing_item(
            name,
            item_details,
            content,
            freshest_screenshot_time,
            event_buffer_mode,
        )
        if _is_landing_fallback_candidate(item_details, freshest_screenshot_time):
            fallback_items.append(item)
        if _is_landing_candidate(item_details, content, freshest_screenshot_time):
            grouped[item["group_name"]].append(item)

    # Keep the landing payload intentionally tiny: a few fresh, grouped stills
    # can rotate cheaply in the browser without fetching or diffing the full
    # template inventory.
    scenes: list[dict[str, Any]] = []
    for group_name, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (
                item["scene_score"],
                item["hero_score"],
                item["event_score"],
                item["profile_score"],
                item["last_screenshot_time"],
            ),
            reverse=True,
        )
        for chunk_index, chunk in enumerate(
            _group_scene_chunks(group_name, ordered, scene_size, content)
        ):
            if not chunk:
                continue
            hero = chunk[0]
            pip = chunk[1] if len(chunk) > 1 else None
            related = chunk[2:] if pip else chunk[1:]
            scene_id = f"{group_name}-{hero['name']}"
            if chunk_index:
                scene_id = f"{scene_id}-{chunk_index + 1}"
            scenes.append(
                _apply_scene_timing(
                    {
                        "event_score": hero.get("event_score", 0),
                        "group_label": _group_label(group_name),
                        "group_name": group_name,
                        "hero": hero,
                        "hero_score": hero["hero_score"],
                        "id": scene_id,
                        "pip": pip,
                        "profile_score": hero["profile_score"],
                        "quality_score": hero["quality_score"],
                        "related": related,
                        "rhythm_copy": profile["default_rhythm_copy"],
                        "scene_score": hero.get("scene_score", hero["hero_score"]),
                        "theme_copy": f"{_group_label(group_name)} - {len(chunk)} views",
                    },
                    profile,
                    content,
                )
            )

    if scenes:
        selected = _compose_profiled_scenes(scenes, content, max_scenes)
        satellite = _satellite_landing_scene(profile, content)
        if satellite:
            selected.insert(min(1, len(selected)), satellite)
        return selected

    ordered_fallbacks = sorted(
        fallback_items,
        key=lambda item: (
            item["scene_score"],
            item["hero_score"],
            item["event_score"],
            item["profile_score"],
            item["last_screenshot_time"],
        ),
        reverse=True,
    )[:scene_size]
    if not ordered_fallbacks:
        return []

    hero = ordered_fallbacks[0]
    pip = ordered_fallbacks[1] if len(ordered_fallbacks) > 1 else None
    related = ordered_fallbacks[2:] if pip else ordered_fallbacks[1:]
    return [
        _apply_scene_timing(
            {
                "event_score": hero.get("event_score", 0),
                "group_label": hero["group_label"],
                "group_name": hero["group_name"],
                "hero": hero,
                "hero_score": hero["hero_score"],
                "id": f"fallback-{hero['name']}",
                "pip": pip,
                "profile_score": hero["profile_score"],
                "quality_score": hero["quality_score"],
                "related": related,
                "rhythm_copy": profile["default_rhythm_copy"],
                "scene_score": hero.get("scene_score", hero["hero_score"]),
                "theme_copy": f"{hero['group_label']} - {len(ordered_fallbacks)} views",
            },
            profile,
            content,
        )
    ]


def create_blueprint() -> Blueprint:
    """Create and return the main views blueprint."""

    from app import routes

    bp = Blueprint("views", __name__)

    @bp.route("/", endpoint="index")
    @routes.login_required
    def index():
        """Render the index page with available templates."""

        active_groups = routes.get_active_groups()
        landing_mode = _landing_mode_profile(request.args.get("mode"), request.host)
        landing_profile = _landing_content_profile(
            request.args.get("profile"),
            request.host,
        )
        template_details = (
            routes.template_manager.TemplateManager().get_templates()
            if landing_profile["key"] in LANDING_PRIORITY_PROFILES
            else routes.template_manager.get_templates()
        )
        landing_buffer_mode = _landing_event_buffer_mode(
            request.args.get("buffer") or request.args.get("event_buffer"),
            landing_mode,
        )
        landing_scenes = _build_landing_scenes(
            template_details,
            landing_mode,
            landing_profile,
            landing_buffer_mode,
        )
        landing_event_poll = _landing_event_poll_ms(landing_profile)
        return routes.render_template(
            "index.html",
            active_groups=active_groups,
            landing_event_poll_ms=landing_event_poll,
            landing_event_buffer_auto_every=LANDING_EVENT_BUFFER_AUTO_EVERY,
            landing_event_buffer_mode=landing_buffer_mode,
            landing_events_enabled=landing_event_poll > 0,
            landing_events_url=routes.url_for(
                "views.landing_events",
                buffer=landing_buffer_mode,
                mode=landing_mode["key"],
                profile=landing_profile["key"],
            ),
            landing_mode=landing_mode,
            landing_profile=landing_profile,
            landing_profiles=tuple(LANDING_CONTENT_PROFILES.values()),
            landing_modes=tuple(LANDING_MODE_PROFILES.values()),
            landing_scenes=landing_scenes,
            priority_handoff_settings={
                door: [name for name in approaches if name in template_details]
                for door, approaches in VIEWER_CONFIG.get(
                    "priority_handoffs", {}
                ).items()
                if door in template_details
                and landing_profile["key"] in LANDING_PRIORITY_PROFILES
            },
            kiosk_live_settings={
                name: options
                for name, options in VIEWER_CONFIG.get("kiosk_live", {}).items()
                if name in template_details
                and landing_profile["key"] in {"office", "living"}
            },
            page_title="Dashboard",
            meta_description="A slower at-a-glance channel for curated camera views.",
        )

    @bp.route("/landing_events", endpoint="landing_events")
    @routes.login_required
    def landing_events():
        """Return recent landing motion events for client-side scene interrupts."""

        template_details = routes.template_manager.TemplateManager().get_templates()
        landing_mode = _landing_mode_profile(request.args.get("mode"), request.host)
        landing_profile = _landing_content_profile(
            request.args.get("profile"),
            request.host,
        )
        landing_buffer_mode = _landing_event_buffer_mode(
            request.args.get("buffer") or request.args.get("event_buffer"),
            landing_mode,
        )
        landing_scenes = _build_landing_scenes(
            template_details,
            landing_mode,
            landing_profile,
            landing_buffer_mode,
        )
        events = _build_landing_events(landing_scenes, landing_profile)
        if landing_profile["key"] in LANDING_PRIORITY_PROFILES:
            from app.utils.google_events import landing_events as google_door_events
            from app.utils.household_presence import arrival_events
            from app.utils.knox_events import landing_events as knox_door_events

            cloud_events = google_door_events(landing_scenes) + knox_door_events(
                landing_scenes
            )
            cloud_events.sort(key=lambda event: event["occurred_at"], reverse=True)
            # Prefer the device's explicit person/chime event over a duplicate
            # screenshot-motion alert. Source and capture times stay separate.
            cloud_cameras = {event["camera_name"] for event in cloud_events}
            events = cloud_events + [
                event for event in events if event["camera_name"] not in cloud_cameras
            ]
            events.extend(arrival_events(landing_scenes))
        return jsonify(
            {
                "capture_times": {
                    scene["hero"]["name"]: scene["hero"]["last_screenshot_time"]
                    for scene in landing_scenes
                },
                "source_freshness": {
                    scene["hero"]["name"]: scene["hero"]["freshness"]
                    for scene in landing_scenes
                },
                "available_cameras": (
                    [scene["hero"]["name"] for scene in landing_scenes]
                    if landing_profile["key"] in LANDING_PRIORITY_PROFILES
                    else None
                ),
                "events": events,
                "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "mode": landing_mode["key"],
                "profile": landing_profile["key"],
            }
        )

    @bp.route("/weather", endpoint="weather_page")
    @routes.login_required
    def weather_page():
        """Render the custom local weather dashboard."""

        template_details = routes.template_manager.get_templates()
        brief = load_or_generate_weather_brief(template_details)
        for section in brief.get("sections", []):
            for tile in section.get("tiles", []):
                name = tile.get("name", "")
                details = template_details.get(name, {})
                tile["source_freshness"] = source_freshness(name, details)
                tile["last_screenshot_time"] = str(
                    details.get("last_screenshot_time") or ""
                )
                if tile["last_screenshot_time"]:
                    tile["image_url"] = (
                        f"/clean_screenshot/{quote(name)}?capture={quote(tile['last_screenshot_time'])}"
                    )
                tile["status"] = str(details.get("last_capture_status") or "unknown")
        return routes.render_template(
            "weather.html",
            active_groups=routes.get_active_groups(),
            brief=brief,
            page_title="Weather Brief",
            meta_description=(
                "A local NOAA-like weather sheet generated from Eyebat sources."
            ),
        )

    @bp.route("/weather/brief.json", endpoint="weather_brief_json")
    @routes.login_required
    def weather_brief_json():
        """Return the generated weather brief artifact as JSON."""

        template_details = routes.template_manager.get_templates()
        return jsonify(load_or_generate_weather_brief(template_details))

    @bp.route("/seiche", endpoint="seiche_page")
    @routes.login_required
    def seiche_page():
        """Render the Lake Michigan SeicheClock dashboard."""

        template_details = routes.template_manager.get_templates()
        return routes.render_template(
            "seiche.html",
            active_groups=routes.get_active_groups(),
            beach_tiles=build_beach_camera_tiles(template_details, limit=12),
            brief=load_or_generate_seiche_brief(),
            page_title="SeicheClock",
            meta_description=(
                "A Lake Michigan water-level clock built from NOAA CO-OPS gauges."
            ),
        )

    @bp.route("/seiche/brief.json", endpoint="seiche_brief_json")
    @routes.login_required
    def seiche_brief_json():
        """Return the generated SeicheClock artifact as JSON."""

        return jsonify(load_or_generate_seiche_brief())

    @bp.route("/satellite", endpoint="satellite_page")
    @routes.login_required
    def satellite_page():
        """Browse the daily Chicago to Kenosha satellite archive."""
        archive = Path("/data/glimpser/satellite/chicago-kenosha")
        dates = (
            sorted(
                path.stem
                for path in archive.glob("????-??-??.jpg")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem)
            )
            if archive.is_dir()
            else []
        )
        return routes.render_template(
            "satellite.html",
            dates=dates,
            page_title="Chicago to the Beach · Satellite",
            meta_description="Daily satellite timelapse of Chicago, Lincolnwood, and the Kenosha shoreline.",
            active_groups=routes.get_active_groups(),
        )

    @bp.route("/satellite/media/<string:filename>", endpoint="satellite_media")
    @routes.login_required
    def satellite_media(filename: str):
        if not (
            re.fullmatch(r"\d{4}-\d{2}-\d{2}\.jpg", filename)
            or filename == "timelapse.mp4"
        ):
            routes.abort(404)
        archive = Path("/data/glimpser/satellite/chicago-kenosha")
        response = send_from_directory(archive, filename, conditional=True)
        response.headers["Cache-Control"] = (
            "private, max-age=86400"
            if filename.endswith(".jpg")
            else "private, no-cache"
        )
        return response

    @bp.route("/dashboard/<string:dashboard_name>/data")
    @routes.login_required
    def visual_dashboard_data(dashboard_name: str):
        if dashboard_name not in DASHBOARDS:
            routes.abort(404)
        response = jsonify(
            build_visual_dashboard(
                routes.template_manager.TemplateManager().get_templates(),
                dashboard_name,
            )
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.route("/dashboard/<string:dashboard_name>")
    @routes.login_required
    def dashboard_page(dashboard_name: str):
        """Render a curated wall while retaining the full source catalog."""
        if dashboard_name not in DASHBOARDS:
            routes.abort(404)
        return routes.render_template(
            "visual_dashboard.html",
            dashboard_model=build_visual_dashboard(
                routes.template_manager.TemplateManager().get_templates(),
                dashboard_name,
            ),
            dashboard_options=DASHBOARDS,
            group_name="all",
            dashboard_name=dashboard_name,
            dashboard_label=DASHBOARDS[dashboard_name],
            page_title=DASHBOARDS[dashboard_name],
            active_groups=routes.get_active_groups(),
        )

    @bp.route("/group/<string:group_name>", endpoint="group_page")
    @routes.login_required
    def group_page(group_name: str):
        """Render a page listing all cameras in a group."""

        group_name = routes.secure_filename(group_name)
        groups = routes.get_active_groups()
        if group_name == "all":
            return routes.redirect(routes.url_for("index"))
        if group_name not in groups:
            routes.abort(404)
        return routes.render_template(
            "group.html",
            group_name=group_name,
            page_title=f"Group - {group_name}",
        )

    return bp
