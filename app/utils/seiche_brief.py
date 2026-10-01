"""Build a Lake Michigan seiche brief from NOAA water-level data."""

from __future__ import annotations

import html
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.config import DATABASE_PATH

SEICHE_BRIEF_DIR = Path(
    os.getenv(
        "GLIMPSER_SEICHE_BRIEF_DIR",
        str(Path(DATABASE_PATH).resolve().parent / "seiche"),
    )
)
SEICHE_BRIEF_JSON = SEICHE_BRIEF_DIR / "daily_seiche.json"
SEICHE_BRIEF_HTML = SEICHE_BRIEF_DIR / "daily_seiche.html"
SEICHE_BRIEF_MAX_AGE = timedelta(minutes=15)
SEICHE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
NOAA_DATAGETTER_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_APPLICATION = "glimpser"

STATIONS: tuple[dict[str, str], ...] = (
    {
        "id": "9087044",
        "name": "Calumet Harbor",
        "role": "south shore",
        "lat": "41.7297",
        "lon": "-87.5383",
    },
    {
        "id": "9087057",
        "name": "Milwaukee",
        "role": "west shore",
        "lat": "43.0020",
        "lon": "-87.8876",
    },
    {
        "id": "9087023",
        "name": "Ludington",
        "role": "north/east anchor",
        "lat": "43.9474",
        "lon": "-86.4415",
    },
)

PLEASANT_PRAIRIE_SITE: dict[str, str] = {
    "id": "pleasant-prairie",
    "name": "Pleasant Prairie",
    "role": "beach house proxy",
    "lat": "42.5350",
    "lon": "-87.8100",
    "source_label": "Milwaukee/Calumet NOAA bracket",
    "source": (
        "Estimated for the Pleasant Prairie lakefront from NOAA CO-OPS "
        "Milwaukee and Calumet Harbor water-level gauges."
    ),
}

BEACH_CAMERA_GROUPS = {
    "beachhouse",
    "beach",
    "buoy",
    "eufy",
    "greatlakes",
    "harbor",
    "lake",
    "lakefront",
    "lakemichigan",
    "marine",
    "pier",
    "regional",
    "shore",
    "waukegan",
    "winthrop",
}
BEACH_CAMERA_PRIORITY = {
    "beachshore": 1200,
    "beachnorthjetty": 1120,
    "beachbioswale": 1040,
    "beachpathway": 1000,
    "beachmapletree": 960,
    "beachgravel": 930,
    "beachdriveway": 900,
    "beachfrontyard": 860,
    "winthropbuoy": 760,
    "waukeganbuoy": 740,
    "waukeganharbor": 720,
    "northpointmarina": 700,
}


def parse_seiche_time(value: Any) -> datetime | None:
    """Parse timestamps emitted by NOAA CO-OPS and local artifacts."""

    if not value:
        return None
    text = str(value).strip()
    for time_format in ("%Y-%m-%d %H:%M", SEICHE_TIME_FORMAT):
        try:
            return datetime.strptime(text, time_format)
        except ValueError:
            continue
    return None


def _fetch_json(url: str, timeout: int = 12) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "glimpser-seiche/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"NOAA request failed: {exc}") from exc


def _date_range(now: datetime, hours: int) -> tuple[str, str]:
    begin = now - timedelta(hours=hours)
    return begin.strftime("%Y%m%d"), now.strftime("%Y%m%d")


def _fetch_noaa_product(
    station_id: str,
    product: str,
    *,
    now: datetime,
    hours: int = 30,
) -> dict[str, Any]:
    begin_date, end_date = _date_range(now, hours)
    params = {
        "product": product,
        "application": NOAA_APPLICATION,
        "begin_date": begin_date,
        "end_date": end_date,
        "station": station_id,
        "time_zone": "gmt",
        "units": "english",
        "format": "json",
    }
    if product == "water_level":
        params["datum"] = "LWD"
    url = f"{NOAA_DATAGETTER_URL}?{urlencode(params)}"
    return _fetch_json(url)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_series(
    payload: dict[str, Any] | None,
    value_key: str,
) -> list[dict[str, Any]]:
    samples = []
    for item in (payload or {}).get("data") or []:
        sample_time = parse_seiche_time(item.get("t"))
        value = _float_or_none(item.get(value_key))
        if sample_time is None or value is None:
            continue
        samples.append({"time": sample_time, "value": value, "raw": item})
    samples.sort(key=lambda sample: sample["time"])
    return samples


def _sample_at_or_before(
    samples: list[dict[str, Any]],
    target_time: datetime,
) -> dict[str, Any] | None:
    candidates = [sample for sample in samples if sample["time"] <= target_time]
    return candidates[-1] if candidates else None


def _sparkline_points(
    samples: list[dict[str, Any]],
    *,
    max_points: int = 36,
) -> list[dict[str, Any]]:
    if not samples:
        return []
    stride = max(1, len(samples) // max_points)
    sampled = samples[::stride]
    if sampled[-1] is not samples[-1]:
        sampled.append(samples[-1])
    values = [sample["value"] for sample in sampled]
    low = min(values)
    high = max(values)
    span = high - low or 1.0
    total = max(1, len(sampled) - 1)
    return [
        {
            "x": round((index / total) * 100, 2),
            "y": round(32 - ((sample["value"] - low) / span) * 28, 2),
            "value_ft": round(sample["value"], 3),
            "time": sample["time"].strftime("%H:%M"),
        }
        for index, sample in enumerate(sampled)
    ]


def _inches(value_ft: float | None) -> float | None:
    return None if value_ft is None else round(value_ft * 12, 1)


def _format_inches(value_ft: float | None, *, signed: bool = False) -> str:
    value_in = _inches(value_ft)
    if value_in is None:
        return "unknown"
    sign = "+" if signed and value_in > 0 else ""
    return f"{sign}{value_in:.1f} in"


def _trend_label(change_ft: float | None) -> str:
    if change_ft is None:
        return "unknown"
    change_in = change_ft * 12
    if change_in > 0.35:
        return "rising"
    if change_in < -0.35:
        return "falling"
    return "near slack"


def _setup_label(anomaly_ft: float | None) -> str:
    if anomaly_ft is None:
        return "unknown"
    anomaly_in = anomaly_ft * 12
    if anomaly_in > 1.2:
        return "setup"
    if anomaly_in < -1.2:
        return "drawdown"
    return "near normal"


def _station_summary(
    station: dict[str, str],
    payload: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    samples = _parse_series(payload, "v")
    if not samples:
        return {
            **station,
            "status": "unavailable",
            "message": "No recent NOAA water-level samples.",
        }

    latest = samples[-1]
    recent_24h = [
        sample for sample in samples if sample["time"] >= now - timedelta(hours=24)
    ]
    if not recent_24h:
        recent_24h = samples

    one_hour_back = _sample_at_or_before(samples, latest["time"] - timedelta(hours=1))
    six_hours_back = _sample_at_or_before(samples, latest["time"] - timedelta(hours=6))
    values = [sample["value"] for sample in recent_24h]
    min_ft = min(values)
    max_ft = max(values)
    mean_ft = sum(values) / len(values)
    range_span_ft = max_ft - min_ft
    position_pct = (
        50.0
        if range_span_ft == 0
        else ((latest["value"] - min_ft) / range_span_ft) * 100
    )
    change_1h = latest["value"] - one_hour_back["value"] if one_hour_back else None
    change_6h = latest["value"] - six_hours_back["value"] if six_hours_back else None
    age_minutes = max(0, int((now - latest["time"]).total_seconds() // 60))

    return {
        **station,
        "status": "ok" if age_minutes <= 120 else "stale",
        "latest_time": latest["time"].strftime(SEICHE_TIME_FORMAT),
        "age_minutes": age_minutes,
        "level_ft_lwd": round(latest["value"], 3),
        "min_24h_ft_lwd": round(min_ft, 3),
        "max_24h_ft_lwd": round(max_ft, 3),
        "position_24h_pct": round(position_pct, 1),
        "range_24h_ft": round(max_ft - min_ft, 3),
        "range_24h_in": _inches(max_ft - min_ft),
        "mean_24h_ft_lwd": round(mean_ft, 3),
        "anomaly_ft": round(latest["value"] - mean_ft, 3),
        "anomaly_in": _inches(latest["value"] - mean_ft),
        "change_1h_ft": None if change_1h is None else round(change_1h, 3),
        "change_1h_in": _inches(change_1h),
        "change_6h_ft": None if change_6h is None else round(change_6h, 3),
        "change_6h_in": _inches(change_6h),
        "trend": _trend_label(change_1h),
        "setup": _setup_label(latest["value"] - mean_ft),
        "sparkline": _sparkline_points(recent_24h),
    }


def _wind_summary(payload: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    samples = _parse_series(payload, "s")
    if not samples:
        return {"status": "unavailable", "message": "No recent NOAA wind samples."}

    latest = samples[-1]
    raw = latest["raw"]
    direction_deg = _float_or_none(raw.get("d"))
    speed_mph = _float_or_none(raw.get("s"))
    gust_mph = _float_or_none(raw.get("g"))
    age_minutes = max(0, int((now - latest["time"]).total_seconds() // 60))
    south_push = None
    if direction_deg is not None and speed_mph is not None:
        # NOAA wind direction is where wind comes from. Add 180 degrees to get
        # motion direction, then project it onto Lake Michigan's long axis.
        toward_deg = (direction_deg + 180) % 360
        lake_axis_south_deg = 190
        south_push = speed_mph * math.cos(
            math.radians(toward_deg - lake_axis_south_deg)
        )

    return {
        "status": "ok" if age_minutes <= 120 else "stale",
        "station": (payload or {}).get("metadata", {}).get("name", "Calumet Harbor"),
        "latest_time": latest["time"].strftime(SEICHE_TIME_FORMAT),
        "age_minutes": age_minutes,
        "speed_mph": None if speed_mph is None else round(speed_mph, 1),
        "gust_mph": None if gust_mph is None else round(gust_mph, 1),
        "direction_deg": None if direction_deg is None else round(direction_deg),
        "direction_cardinal": str(raw.get("dr") or ""),
        "south_push_mph": None if south_push is None else round(south_push, 1),
        "south_push_pct": (
            None
            if south_push is None
            else round(max(0, min(100, 50 + south_push * 2.5)), 1)
        ),
        "setup_hint": _wind_setup_hint(south_push),
    }


def _wind_setup_hint(south_push_mph: float | None) -> str:
    if south_push_mph is None:
        return "unknown"
    if south_push_mph >= 8:
        return "wind favors south-shore setup"
    if south_push_mph <= -8:
        return "wind favors south-shore drawdown"
    return "wind is weakly aligned with lake setup"


def _split_groups(details: dict[str, Any] | None) -> set[str]:
    groups = str((details or {}).get("groups") or "")
    return {group.strip().lower() for group in groups.split(",") if group.strip()}


def _camera_age(details: dict[str, Any], now: datetime) -> tuple[int | None, str]:
    shot_time = parse_seiche_time(details.get("last_screenshot_time"))
    if shot_time is None:
        return None, "unknown"
    age_minutes = max(0, int((now - shot_time).total_seconds() // 60))
    if age_minutes < 120:
        return age_minutes, f"{age_minutes}m"
    if age_minutes < 2880:
        return age_minutes, f"{age_minutes // 60}h"
    return age_minutes, f"{age_minutes // 1440}d"


def _camera_freshness(age_minutes: int | None, status: str) -> dict[str, Any]:
    """Return a display-only freshness score for solar shoreline cameras."""

    normalized = status.strip().lower()
    if normalized == "failed":
        return {"pct": 8, "state": "offline"}
    if age_minutes is None:
        return {"pct": 18, "state": "unknown"}
    if age_minutes <= 120 and normalized in {"fresh", "ok", "stale_ok", ""}:
        return {"pct": 100, "state": "fresh"}
    if age_minutes <= 360:
        return {"pct": 72, "state": "warm"}
    if age_minutes <= 1440:
        return {"pct": 48, "state": "stale"}
    if age_minutes <= 4320:
        return {"pct": 26, "state": "old"}
    return {"pct": 12, "state": "old"}


def _beach_camera_score(name: str, details: dict[str, Any], now: datetime) -> int:
    groups = _split_groups(details)
    age_minutes, _ = _camera_age(details, now)
    status = str(details.get("last_capture_status") or "").strip().lower()
    lowered = name.lower()
    score = BEACH_CAMERA_PRIORITY.get(lowered, 0)
    if groups.intersection({"beachhouse", "eufy"}):
        score += 450
    if groups.intersection({"beach", "shore", "lakefront"}):
        score += 220
    if groups.intersection({"buoy", "harbor", "marine", "pier"}):
        score += 150
    if status == "fresh":
        score += 180
    elif status == "stale_ok":
        score += 90
    elif status == "failed":
        score -= 260
    if age_minutes is None:
        score -= 120
    elif age_minutes <= 120:
        score += 140
    elif age_minutes <= 720:
        score += 40
    elif age_minutes >= 2880:
        score -= 180
    return score


def build_beach_camera_tiles(
    templates: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Choose the most useful shoreline cameras for the SeicheClock view."""

    current_time = now or datetime.utcnow()
    tiles = []
    for name, details in templates.items():
        groups = _split_groups(details)
        lowered = name.lower()
        source_text = (
            f"{name} {details.get('url', '')} {details.get('notes', '')}".lower()
        )
        if (
            not groups.intersection(BEACH_CAMERA_GROUPS)
            and "shore" not in lowered
            and "beach" not in source_text
            and "buoy" not in lowered
        ):
            continue
        age_minutes, age_label = _camera_age(details, current_time)
        status = str(details.get("last_capture_status") or "unknown")
        freshness = _camera_freshness(age_minutes, status)
        caption = str(details.get("last_caption") or details.get("notes") or "").strip()
        tiles.append(
            {
                "name": name,
                "groups": sorted(groups),
                "image_url": f"/last_screenshot/{quote(name)}",
                "status": status,
                "age_minutes": age_minutes,
                "age_label": age_label,
                "caption": caption[:180],
                "freshness_pct": freshness["pct"],
                "freshness_state": freshness["state"],
                "score": _beach_camera_score(name, details, current_time),
            }
        )

    tiles.sort(key=lambda tile: (tile["score"], tile["name"]), reverse=True)
    return tiles[:limit]


def _moon_context(now: datetime) -> dict[str, Any]:
    new_moon = datetime(2000, 1, 6, 18, 14)
    synodic_days = 29.530588853
    age_days = ((now - new_moon).total_seconds() / 86400) % synodic_days
    fraction = age_days / synodic_days
    phase_angle = fraction * 360
    illumination = 0.5 * (1 - math.cos(math.radians(phase_angle)))
    names = (
        (0.03, "new moon"),
        (0.22, "waxing crescent"),
        (0.28, "first quarter"),
        (0.47, "waxing gibbous"),
        (0.53, "full moon"),
        (0.72, "waning gibbous"),
        (0.78, "last quarter"),
        (0.97, "waning crescent"),
        (1.00, "new moon"),
    )
    phase_name = next(name for limit, name in names if fraction <= limit)
    spring_signal = abs(math.cos(math.radians(phase_angle * 2)))
    return {
        "phase": phase_name,
        "phase_fraction": round(fraction, 3),
        "phase_angle": round(phase_angle, 1),
        "illumination_pct": round(illumination * 100, 1),
        "moon_age_days": round(age_days, 1),
        "spring_signal": round(spring_signal, 2),
        "spring_label": (
            "strong micro-tide context" if spring_signal >= 0.82 else "minor context"
        ),
        "note": "Great Lakes astronomical tides are tiny; wind and pressure dominate.",
    }


def _by_station_id(stations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {station["id"]: station for station in stations}


def _station_fraction_between(
    south_station: dict[str, Any],
    north_station: dict[str, Any],
    site: dict[str, str],
) -> float:
    south_lat = _float_or_none(south_station.get("lat"))
    north_lat = _float_or_none(north_station.get("lat"))
    site_lat = _float_or_none(site.get("lat"))
    if south_lat is None or north_lat is None or site_lat is None:
        return 0.5
    span = north_lat - south_lat
    if span == 0:
        return 0.5
    return max(0.0, min(1.0, (site_lat - south_lat) / span))


def _blend_numeric(
    south_station: dict[str, Any],
    north_station: dict[str, Any],
    key: str,
    fraction: float,
) -> float | None:
    south_value = _float_or_none(south_station.get(key))
    north_value = _float_or_none(north_station.get(key))
    if south_value is None or north_value is None:
        return None
    return south_value + (north_value - south_value) * fraction


def _blend_sparkline(
    south_station: dict[str, Any],
    north_station: dict[str, Any],
    fraction: float,
) -> list[dict[str, Any]]:
    south_points = south_station.get("sparkline") or []
    north_points = north_station.get("sparkline") or []
    point_count = min(len(south_points), len(north_points))
    if point_count == 0:
        return []

    blended_values = []
    for index in range(point_count):
        south_value = _float_or_none(south_points[index].get("value_ft"))
        north_value = _float_or_none(north_points[index].get("value_ft"))
        if south_value is None or north_value is None:
            continue
        blended_values.append(
            {
                "value": south_value + (north_value - south_value) * fraction,
                "time": south_points[index].get("time")
                or north_points[index].get("time"),
            }
        )
    if not blended_values:
        return []

    values = [point["value"] for point in blended_values]
    low = min(values)
    high = max(values)
    span = high - low or 1.0
    total = max(1, len(blended_values) - 1)
    return [
        {
            "x": round((index / total) * 100, 2),
            "y": round(32 - ((point["value"] - low) / span) * 28, 2),
            "value_ft": round(point["value"], 3),
            "time": point["time"],
        }
        for index, point in enumerate(blended_values)
    ]


def _pleasant_prairie_estimate(stations: list[dict[str, Any]]) -> dict[str, Any]:
    indexed = _by_station_id(stations)
    calumet = indexed.get("9087044", {})
    milwaukee = indexed.get("9087057", {})
    fraction = _station_fraction_between(
        calumet,
        milwaukee,
        PLEASANT_PRAIRIE_SITE,
    )
    level_ft = _blend_numeric(calumet, milwaukee, "level_ft_lwd", fraction)
    if level_ft is None:
        return {
            **PLEASANT_PRAIRIE_SITE,
            "status": "unavailable",
            "message": "No current NOAA bracket estimate for Pleasant Prairie.",
            "bracket_fraction": round(fraction, 3),
        }

    min_ft = _blend_numeric(calumet, milwaukee, "min_24h_ft_lwd", fraction)
    max_ft = _blend_numeric(calumet, milwaukee, "max_24h_ft_lwd", fraction)
    mean_ft = _blend_numeric(calumet, milwaukee, "mean_24h_ft_lwd", fraction)
    change_1h = _blend_numeric(calumet, milwaukee, "change_1h_ft", fraction)
    change_6h = _blend_numeric(calumet, milwaukee, "change_6h_ft", fraction)
    range_ft = None
    position_pct = None
    if min_ft is not None and max_ft is not None:
        range_ft = max_ft - min_ft
        span = max_ft - min_ft
        position_pct = 50.0 if span == 0 else ((level_ft - min_ft) / span) * 100
    anomaly_ft = None if mean_ft is None else level_ft - mean_ft
    bracket_statuses = {calumet.get("status"), milwaukee.get("status")}
    status = "ok" if bracket_statuses == {"ok"} else "stale"
    age_candidates = [
        _float_or_none(calumet.get("age_minutes")),
        _float_or_none(milwaukee.get("age_minutes")),
    ]
    age_minutes = max([age for age in age_candidates if age is not None], default=None)

    return {
        **PLEASANT_PRAIRIE_SITE,
        "status": status,
        "latest_time": calumet.get("latest_time") or milwaukee.get("latest_time"),
        "age_minutes": None if age_minutes is None else int(age_minutes),
        "level_ft_lwd": round(level_ft, 3),
        "min_24h_ft_lwd": None if min_ft is None else round(min_ft, 3),
        "max_24h_ft_lwd": None if max_ft is None else round(max_ft, 3),
        "position_24h_pct": (
            None if position_pct is None else round(max(0, min(100, position_pct)), 1)
        ),
        "range_24h_ft": None if range_ft is None else round(range_ft, 3),
        "range_24h_in": _inches(range_ft),
        "mean_24h_ft_lwd": None if mean_ft is None else round(mean_ft, 3),
        "anomaly_ft": None if anomaly_ft is None else round(anomaly_ft, 3),
        "anomaly_in": _inches(anomaly_ft),
        "change_1h_ft": None if change_1h is None else round(change_1h, 3),
        "change_1h_in": _inches(change_1h),
        "change_6h_ft": None if change_6h is None else round(change_6h, 3),
        "change_6h_in": _inches(change_6h),
        "trend": _trend_label(change_1h),
        "setup": _setup_label(anomaly_ft),
        "bracket_fraction": round(fraction, 3),
        "sparkline": _blend_sparkline(calumet, milwaukee, fraction),
    }


def _lake_tilt(stations: list[dict[str, Any]]) -> dict[str, Any]:
    indexed = _by_station_id(stations)
    calumet = indexed.get("9087044", {})
    milwaukee = indexed.get("9087057", {})
    ludington = indexed.get("9087023", {})

    def delta(target: dict[str, Any]) -> float | None:
        south_level = calumet.get("level_ft_lwd")
        target_level = target.get("level_ft_lwd")
        if south_level is None or target_level is None:
            return None
        return round(float(south_level) - float(target_level), 3)

    south_vs_milwaukee = delta(milwaukee)
    south_vs_ludington = delta(ludington)
    comparison = south_vs_milwaukee
    if comparison is None:
        comparison = south_vs_ludington

    if comparison is None:
        label = "unknown lake tilt"
    elif comparison * 12 > 1.5:
        label = "south shore is running higher"
    elif comparison * 12 < -1.5:
        label = "south shore is running lower"
    else:
        label = "lake surface is close to balanced"

    return {
        "label": label,
        "south_vs_milwaukee_ft": south_vs_milwaukee,
        "south_vs_milwaukee_in": _inches(south_vs_milwaukee),
        "south_vs_ludington_ft": south_vs_ludington,
        "south_vs_ludington_in": _inches(south_vs_ludington),
    }


def _watch_items(
    primary: dict[str, Any],
    lake_tilt: dict[str, Any],
    wind: dict[str, Any],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    site_name = primary.get("name", "Pleasant Prairie")
    if primary.get("range_24h_in") and abs(float(primary["range_24h_in"])) >= 4:
        items.append(
            {
                "title": "Large lakefront swing",
                "body": (
                    f"{site_name} proxy range is "
                    f"{primary['range_24h_in']:.1f} in over 24h."
                ),
            }
        )
    if primary.get("change_1h_in") and abs(float(primary["change_1h_in"])) >= 1:
        items.append(
            {
                "title": f"Fast {primary['trend']}",
                "body": (
                    f"{site_name} proxy changed "
                    f"{primary['change_1h_in']:+.1f} in over the last hour."
                ),
            }
        )
    tilt_in = lake_tilt.get("south_vs_milwaukee_in")
    if tilt_in is not None and abs(float(tilt_in)) >= 2:
        items.append(
            {
                "title": "Lake tilt",
                "body": f"South shore is {tilt_in:+.1f} in vs Milwaukee.",
            }
        )
    south_push = wind.get("south_push_mph")
    if south_push is not None and abs(float(south_push)) >= 8:
        items.append(
            {
                "title": "Wind setup driver",
                "body": f"{wind['setup_hint']} at {south_push:+.1f} mph projected along the lake.",
            }
        )
    if not items:
        items.append(
            {
                "title": "Quiet water level",
                "body": "No large short-term seiche signals crossed the current thresholds.",
            }
        )
    return items[:5]


def _seiche_signal(
    primary: dict[str, Any],
    lake_tilt: dict[str, Any],
    wind: dict[str, Any],
) -> dict[str, Any]:
    """Compress the main drivers into a display-only 0-100 watch score."""

    range_in = _float_or_none(primary.get("range_24h_in"))
    change_1h_in = _float_or_none(primary.get("change_1h_in"))
    tilt_in = _float_or_none(lake_tilt.get("south_vs_milwaukee_in"))
    south_push_mph = _float_or_none(wind.get("south_push_mph"))

    score = 0.0
    if range_in is not None:
        score += min(abs(range_in) / 8, 1) * 35
    if change_1h_in is not None:
        score += min(abs(change_1h_in) / 2, 1) * 25
    if tilt_in is not None:
        score += min(abs(tilt_in) / 6, 1) * 25
    if south_push_mph is not None:
        score += min(abs(south_push_mph) / 18, 1) * 15

    signal_score = round(min(score, 100))
    if signal_score >= 70:
        label = "active"
    elif signal_score >= 40:
        label = "watch"
    elif signal_score >= 18:
        label = "textured"
    else:
        label = "quiet"
    return {"score": signal_score, "label": label}


def _headline(
    primary: dict[str, Any],
    lake_tilt: dict[str, Any],
    wind: dict[str, Any],
) -> str:
    site_name = primary.get("name", "Pleasant Prairie")
    if primary.get("status") not in {"ok", "stale"}:
        return "SeicheClock is waiting on the Pleasant Prairie bracket estimate."
    trend = primary.get("trend", "unknown")
    range_24h = primary.get("range_24h_in")
    tilt_label = lake_tilt.get("label", "unknown lake tilt")
    wind_hint = wind.get("setup_hint", "unknown wind setup")
    if range_24h is None:
        return f"{site_name} lakefront is {trend}; {tilt_label}; {wind_hint}."
    return (
        f"{site_name} lakefront is {trend} with a {range_24h:.1f} in 24h swing; "
        f"{tilt_label}; {wind_hint}."
    )


def build_seiche_brief(
    water_payloads: dict[str, dict[str, Any]],
    wind_payloads: dict[str, dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic SeicheClock brief from NOAA payloads."""

    generated_at = now or datetime.utcnow()
    stations = [
        _station_summary(station, water_payloads.get(station["id"]), generated_at)
        for station in STATIONS
    ]
    wind = _wind_summary((wind_payloads or {}).get("9087044"), generated_at)
    lake_tilt = _lake_tilt(stations)
    pleasant_prairie = _pleasant_prairie_estimate(stations)
    moon = _moon_context(generated_at)
    watch_items = _watch_items(pleasant_prairie, lake_tilt, wind)
    signal = _seiche_signal(pleasant_prairie, lake_tilt, wind)
    ok_sources = len([station for station in stations if station.get("status") == "ok"])
    indexed_stations = _by_station_id(stations)

    return {
        "generated_at": generated_at.strftime(SEICHE_TIME_FORMAT),
        "generated_at_display": generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "headline": _headline(pleasant_prairie, lake_tilt, wind),
        "source": (
            "NOAA CO-OPS water level and meteorological observations; "
            "Pleasant Prairie is estimated from Milwaukee and Calumet Harbor."
        ),
        "summary": {
            "water_level_sources": len(stations),
            "fresh_water_level_sources": ok_sources,
            "primary_site": pleasant_prairie.get("name"),
            "primary_level_ft_lwd": pleasant_prairie.get("level_ft_lwd"),
            "primary_trend": pleasant_prairie.get("trend"),
            "primary_range_24h_in": pleasant_prairie.get("range_24h_in"),
            "calumet_level_ft_lwd": indexed_stations.get("9087044", {}).get(
                "level_ft_lwd"
            ),
            "calumet_trend": indexed_stations.get("9087044", {}).get("trend"),
            "calumet_range_24h_in": indexed_stations.get("9087044", {}).get(
                "range_24h_in"
            ),
            "signal_score": signal["score"],
            "signal_label": signal["label"],
        },
        "pleasant_prairie": pleasant_prairie,
        "stations": stations,
        "lake_tilt": lake_tilt,
        "wind": wind,
        "celestial": moon,
        "watch_items": watch_items,
        "units": {
            "water_level": "feet above Low Water Datum",
            "range": "inches",
            "wind": "mph",
        },
    }


def _brief_to_html(brief: dict[str, Any]) -> str:
    parts = [
        "<article class='seiche-brief-artifact'>",
        f"<h1>{html.escape(str(brief.get('headline') or 'Seiche Brief'))}</h1>",
        f"<p>Generated {html.escape(str(brief.get('generated_at_display') or ''))}</p>",
        "<ul>",
    ]
    for item in brief.get("watch_items") or []:
        parts.append(
            "<li>"
            f"<strong>{html.escape(str(item.get('title') or ''))}</strong>: "
            f"{html.escape(str(item.get('body') or ''))}"
            "</li>"
        )
    parts.extend(["</ul>", "</article>"])
    return "\n".join(parts)


def write_seiche_brief(brief: dict[str, Any]) -> None:
    """Persist the generated seiche brief as JSON and HTML."""

    SEICHE_BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    SEICHE_BRIEF_JSON.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    SEICHE_BRIEF_HTML.write_text(_brief_to_html(brief) + "\n", encoding="utf-8")


def fetch_seiche_payloads(
    *,
    now: datetime | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fetch NOAA water and wind payloads for SeicheClock."""

    current_time = now or datetime.utcnow()
    water_payloads = {}
    for station in STATIONS:
        water_payloads[station["id"]] = _fetch_noaa_product(
            station["id"],
            "water_level",
            now=current_time,
        )
    wind_payloads = {
        "9087044": _fetch_noaa_product("9087044", "wind", now=current_time, hours=12)
    }
    return water_payloads, wind_payloads


def generate_seiche_brief_artifacts(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch NOAA data and persist the current SeicheClock artifacts."""

    current_time = now or datetime.utcnow()
    water_payloads, wind_payloads = fetch_seiche_payloads(now=current_time)
    brief = build_seiche_brief(water_payloads, wind_payloads, now=current_time)
    write_seiche_brief(brief)
    return brief


def load_seiche_brief() -> dict[str, Any] | None:
    """Load the persisted seiche brief if it exists and is valid JSON."""

    try:
        return json.loads(SEICHE_BRIEF_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_or_generate_seiche_brief(
    *,
    max_age: timedelta = SEICHE_BRIEF_MAX_AGE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a fresh enough seiche brief, regenerating when stale."""

    current_time = now or datetime.utcnow()
    brief = load_seiche_brief()
    generated_at = parse_seiche_time((brief or {}).get("generated_at"))
    if brief and generated_at and current_time - generated_at <= max_age:
        return brief
    try:
        return generate_seiche_brief_artifacts(now=current_time)
    except Exception as exc:
        if brief:
            brief["stale_reason"] = str(exc)
            return brief
        return {
            "generated_at": current_time.strftime(SEICHE_TIME_FORMAT),
            "generated_at_display": current_time.strftime("%Y-%m-%d %H:%M UTC"),
            "headline": "SeicheClock could not fetch NOAA data yet.",
            "source": "NOAA CO-OPS water level and meteorological observations",
            "summary": {
                "water_level_sources": len(STATIONS),
                "fresh_water_level_sources": 0,
                "primary_site": PLEASANT_PRAIRIE_SITE["name"],
                "primary_level_ft_lwd": None,
                "primary_trend": "unknown",
                "primary_range_24h_in": None,
            },
            "pleasant_prairie": {
                **PLEASANT_PRAIRIE_SITE,
                "status": "unavailable",
                "message": "NOAA fetch failed before the Pleasant Prairie estimate could be built.",
            },
            "stations": [],
            "lake_tilt": {"label": "unknown lake tilt"},
            "wind": {"status": "unavailable"},
            "celestial": _moon_context(current_time),
            "watch_items": [{"title": "NOAA fetch failed", "body": str(exc)}],
            "units": {
                "water_level": "feet above Low Water Datum",
                "range": "inches",
                "wind": "mph",
            },
        }
