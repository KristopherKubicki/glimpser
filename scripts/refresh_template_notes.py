"""Refresh camera template notes into concise caption prompts.

The ``templates.notes`` field is not just documentation. The scheduler prepends
it to image-caption requests, so stale operational history and generic wording
can directly degrade LLM captions. This script rewrites notes into a consistent
operator prompt shape while preserving useful source caveats.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.utils.validators import url_matches_host

IGNORE_LINE = (
    "Ignore embedded timestamps, browser or player chrome, cookie banners, ads, "
    "and old caption overlays unless they block the scene."
)

ARCHIVE_LINE = (
    "Source state: archived or stale; only describe current visible content if "
    "the frame is clearly live, otherwise return UNREADABLE."
)

OP_HISTORY_RE = re.compile(
    r"^(eyebat|demoted|archived by|retired|throttled|duplicate of|capture tuning|"
    r"switched from|current hal|relevant switchboard|removed temporary)",
    re.IGNORECASE,
)
REFRESHED_NOTE_PREFIXES = (
    "caption focus:",
    "ignore embedded timestamps",
    "source state:",
    "solar eufy cameras",
    "private view:",
    "youtube-derived still:",
    "weatherbug camera:",
    "browser/hls source",
    "uses a direct live thumbnail",
    "do not repeat sensitive",
)
GENERIC_PREFIX_RE = re.compile(
    r"^(this is|here is|what are|please note|do you see|the following)",
    re.IGNORECASE,
)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class TemplateRow:
    name: str
    groups: set[str]
    url: str
    notes: str
    view_description: str
    view_direction: str


FOCUS_RULES: tuple[tuple[set[str], str], ...] = (
    (
        {"latency"},
        "AWS regional latency, failed regions, unusual spikes, and especially us-east-2/Ohio above the expected threshold.",
    ),
    (
        {"beachhouse", "beach", "lakefront"},
        "lake level, waves, shore condition, sky, visibility, ice, people, and shoreline access.",
    ),
    (
        {"marine", "naval", "ais", "harbor", "shipping", "buoy"},
        "vessel traffic, named ships, harbor activity, waves, fog, ice, and navigation hazards.",
    ),
    (
        {"cosmic", "solar"},
        "space-weather activity, aurora potential, magnetic or particle anomalies, and visible thresholds.",
    ),
    (
        {"weather", "sky", "radar"},
        "cloud structure, precipitation, visibility, wind cues, alerts, and approaching weather.",
    ),
    (
        {"traffic"},
        "road speed, backups, lane closures, incidents, signs, and unusual congestion.",
    ),
    (
        {"flights", "airport"},
        "airport weather, flight density, runway or route disruptions, turbulence, and alert areas.",
    ),
    (
        {"network", "systems", "ops", "camerahealth"},
        "status, anomalies, thresholds, outages, trends, and whether operator action is needed.",
    ),
    (
        {"power"},
        "outages, demand, price spikes, grid stress, and charge or discharge implications.",
    ),
    (
        {"health", "publichealth"},
        "regional health status, trend changes, visible alert levels, and relevant Chicago-area impact.",
    ),
    (
        {"plants", "grower", "cloner"},
        "plant health, color, leaf posture, moisture cues, growth changes, lights, and equipment state.",
    ),
    (
        {"retail"},
        "storefront, entry, display, occupancy, lighting, open or closed state, and unusual activity.",
    ),
    (
        {"private"},
        "site conditions, people, vehicles, packages, doors, weather, and operationally relevant changes.",
    ),
    (
        {"rail"},
        "train movement, platforms, signals, congestion, visibility, and notable rail activity.",
    ),
    (
        {"news"},
        "visible major headlines, urgent local impact, breaking alerts, and clear page failures.",
    ),
    (
        {"ecom"},
        "prominent product, price, promotion, availability, trust-score, or page-health changes.",
    ),
    (
        {"map", "usa"},
        "map labels, visible alert regions, local impact, movement, and changes from normal.",
    ),
)


def _collapse(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned.replace("metor showers", "meteor showers")


def _split_groups(groups: str) -> set[str]:
    return {group.strip().lower() for group in groups.split(",") if group.strip()}


def _first_useful_sentence(text: str) -> str:
    cleaned = _collapse(text.strip('" '))
    if not cleaned:
        return ""
    first = SENTENCE_RE.split(cleaned, maxsplit=1)[0].strip()
    if len(first) > 220:
        first = first[:217].rstrip() + "..."
    if GENERIC_PREFIX_RE.match(first) and len(first) < 90:
        return ""
    return first


def _clean_note_body(notes: str) -> tuple[str, list[str]]:
    kept: list[str] = []
    caveats: list[str] = []
    for raw_line in (notes or "").splitlines():
        line = _collapse(raw_line)
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("view:"):
            kept.append(line.split(":", 1)[1].strip())
            continue
        if lower.startswith(REFRESHED_NOTE_PREFIXES):
            if lower.startswith(("browser/hls source", "uses a direct live thumbnail")):
                caveats.append(line)
            continue
        if OP_HISTORY_RE.match(line):
            if "direct live thumbnail" in lower:
                caveats.append(
                    "Uses a direct live thumbnail; do not describe YouTube player chrome."
                )
            if "wetmet" in lower or "hls" in lower:
                caveats.append(
                    "Browser/HLS source can be heavy; if it renders blank or chrome-only, return UNREADABLE."
                )
            continue
        kept.append(line)
    return _collapse(" ".join(kept)), caveats


def _subject(row: TemplateRow, cleaned_note: str) -> str:
    if row.name.lower() == "cloudping":
        return "AWS CloudPing latency dashboard, with us-east-2/Ohio as the primary home-region watchpoint."
    if row.view_description:
        subject = row.view_description
        if row.view_direction:
            subject = f"{subject} Direction: {row.view_direction}."
        return _collapse(subject)

    useful = _first_useful_sentence(cleaned_note)
    if useful:
        return useful

    groups = row.groups
    name = row.name
    if "eufy" in groups:
        return f"Eufy camera {name}."
    if {"dashboard", "systems", "ops", "network"} & groups:
        return f"Operational dashboard {name}."
    if {"weather", "sky", "radar"} & groups:
        return f"Weather or sky view {name}."
    if {"marine", "naval", "ais", "harbor", "shipping", "buoy"} & groups:
        return f"Marine view {name}."
    if {"retail"} & groups:
        return f"Retail camera {name}."
    if {"private"} & groups:
        return f"Private site camera {name}."
    if "news" in groups:
        return f"News page monitor {name}."
    if "ecom" in groups:
        return f"Website monitor {name}."
    return f"Camera or dashboard view {name}."


def _focus(groups: set[str]) -> str:
    focus_parts: list[str] = []
    for rule_groups, text in FOCUS_RULES:
        if groups & rule_groups and text not in focus_parts:
            focus_parts.append(text)
        if len(focus_parts) >= 2:
            break
    if not focus_parts:
        focus_parts.append(
            "the most visually important change, anomaly, alert, condition, or action cue."
        )
    return " Also watch ".join(focus_parts)


def _inferred_groups(row: TemplateRow) -> set[str]:
    text = " ".join(
        (
            row.name,
            row.url,
            row.notes,
            row.view_description,
            row.view_direction,
        )
    ).lower()
    inferred: set[str] = set()
    keyword_groups = (
        (("ship", "maritime", "vessel", "ais", "harbor", "buoy"), {"marine", "naval"}),
        (
            ("beach", "shore", "lake michigan", "lakefront", "pier"),
            {"beach", "lakefront"},
        ),
        (
            ("weatherbug", "weather", "radar", "doppler", "sky"),
            {"weather", "sky"},
        ),
        (
            (
                "traffic camera",
                "travelmidwest",
                "highway",
                "i-",
                "road",
                "lane",
                "congestion",
            ),
            {"traffic"},
        ),
        (("airport", "flight", "ohare", "midway", "turbulence"), {"flights"}),
        (("ping", "wifi", "bandwidth", "modem", "router", "adblock"), {"network"}),
        (("cloudping", "latency", "us-east-2", "ohio"), {"latency", "network"}),
        (("power", "comed", "electric", "energy", "outage"), {"power"}),
        (
            (
                "aqi",
                "air quality",
                "pollution",
                "respiratory",
                "cdc",
                "influenza",
                "rsv",
            ),
            {"health", "map"},
        ),
        (("headline", "news", "bbc", "apnews", "bloomberg"), {"news"}),
        (
            ("ecommerce", "product", "price", "promo", "browserleaks", "creepjs"),
            {"ecom"},
        ),
        (
            (
                "aurora",
                "meteor",
                "metor",
                "celestial",
                "sunspot",
                "space weather",
                "magnetic",
                "neutron",
            ),
            {"cosmic"},
        ),
        (("plant", "grower", "cloner", "garden", "botany"), {"plants"}),
        (("dashboard", "chart", "graph"), {"map"}),
    )
    for keywords, groups in keyword_groups:
        if any(keyword in text for keyword in keywords):
            inferred.update(groups)
    return inferred


def _source_caveats(row: TemplateRow, extra_caveats: Iterable[str]) -> list[str]:
    groups = row.groups
    url = row.url.lower()
    caveats = list(dict.fromkeys(extra_caveats))
    if {"archive", "source-stale", "source-broken"} & groups:
        caveats.append(ARCHIVE_LINE)
    if "eufy" in groups or url.startswith("eufy://"):
        caveats.append(
            "Solar Eufy cameras may show a last-good frame while offline; mention staleness only when visible."
        )
    if "private" in groups:
        caveats.append(
            "Private view: report operational facts without exposing unnecessary personal detail."
        )
    if url_matches_host(url, "i.ytimg.com") or url_matches_host(url, "youtube.com"):
        caveats.append(
            "YouTube-derived still: describe only the current frame, not inferred video motion."
        )
    if url_matches_host(url, "weatherbug.com"):
        caveats.append(
            "WeatherBug camera: prioritize the outdoor scene over page framing."
        )
    if "browserleaks" in url or "creepjs" in url:
        caveats.append(
            "Do not repeat sensitive IP or fingerprint details unless the value visibly changes or fails."
        )
    return list(dict.fromkeys(caveats))


def build_refreshed_note(row: TemplateRow) -> str:
    """Return a concise, scene-first caption prompt for one template."""

    cleaned_note, carried_caveats = _clean_note_body(row.notes)
    effective_row = TemplateRow(
        name=row.name,
        groups=row.groups
        | _inferred_groups(
            TemplateRow(
                name=row.name,
                groups=row.groups,
                url=row.url,
                notes=cleaned_note,
                view_description=row.view_description,
                view_direction=row.view_direction,
            )
        ),
        url=row.url,
        notes=row.notes,
        view_description=row.view_description,
        view_direction=row.view_direction,
    )
    lines = [
        f"View: {_subject(effective_row, cleaned_note)}",
        f"Caption focus: {_focus(effective_row.groups)}",
    ]
    lines.extend(_source_caveats(effective_row, carried_caveats))
    lines.append(IGNORE_LINE)
    return "\n".join(_collapse(line) for line in lines if _collapse(line))


def _iter_rows(conn: sqlite3.Connection, names: list[str]) -> list[TemplateRow]:
    conn.row_factory = sqlite3.Row
    where = ""
    params: list[str] = []
    if names:
        where = "where name in ({})".format(",".join("?" for _ in names))
        params = names
    rows = conn.execute(
        f"""
        select name, groups, url, notes, view_description, view_direction
        from templates
        {where}
        order by lower(name)
        """,
        params,
    ).fetchall()
    return [
        TemplateRow(
            name=str(row["name"] or ""),
            groups=_split_groups(str(row["groups"] or "")),
            url=str(row["url"] or ""),
            notes=str(row["notes"] or ""),
            view_description=str(row["view_description"] or ""),
            view_direction=str(row["view_direction"] or ""),
        )
        for row in rows
        if row["name"]
    ]


def refresh_notes(db_path: Path, *, apply: bool, names: list[str]) -> int:
    conn = sqlite3.connect(db_path)
    try:
        rows = _iter_rows(conn, names)
        updates = []
        for row in rows:
            refreshed = build_refreshed_note(row)
            if refreshed != row.notes:
                updates.append((row.name, row.notes, refreshed))

        if not apply:
            for name, old, new in updates[:20]:
                print(f"--- {name}")
                print(f"OLD: {_collapse(old)[:220]}")
                print(f"NEW: {_collapse(new)[:320]}")
            print(f"would_update={len(updates)} total={len(rows)}")
            return len(updates)

        backup = db_path.with_name(
            f"{db_path.name}.notes-refresh-{datetime.utcnow():%Y%m%d_%H%M%S}.bak"
        )
        shutil.copy2(db_path, backup)
        conn.executemany(
            "update templates set notes = ? where name = ?",
            [(new, name) for name, _, new in updates],
        )
        conn.commit()
        print(f"backup={backup}")
        print(f"updated={len(updates)} total={len(rows)}")
        return len(updates)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/glimpser.db"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--name", action="append", default=[])
    args = parser.parse_args()
    refresh_notes(args.db, apply=args.apply, names=args.name)


if __name__ == "__main__":
    main()
