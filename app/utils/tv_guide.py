from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TV_GUIDE_NEW_TONIGHT_URL = "https://www.tvguide.com/new-tonight/"
DEFAULT_TIMEOUT_SECONDS = 12

_CARD_SPLIT_RE = re.compile(r'<div class="c-globalCard ', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _read_url(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    value = _COMMENT_RE.sub(" ", value)
    value = _TAG_RE.sub(" ", value)
    return " ".join(unescape(value).split())


def _first(pattern: str, value: str) -> str:
    match = re.search(pattern, value, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


def _parse_card(block: str) -> dict[str, Any] | None:
    if "c-TvObjectCard" not in block[:300]:
        return None

    metas = [
        _clean_html(match)
        for match in re.findall(
            r'<span class="[^"]*c-TvObjectCard_meta[^"]*">(.*?)</span>',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]
    title_match = re.search(
        r'<h3 class="[^"]*g-text-xlarge[^"]*">\s*<a\s+href="([^"]+)">(.*?)</a>',
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        return None

    href = unescape(title_match.group(1))
    title = _clean_html(title_match.group(2))
    image = unescape(_first(r'<img\s+src="([^"]+)"', block))
    summary = _clean_html(
        _first(r'<div class="[^"]*c-TvObjectCard_summary[^"]*">(.*?)</div>', block)
    )

    date = metas[0] if len(metas) > 0 else ""
    time = metas[1] if len(metas) > 1 else ""
    network = metas[2] if len(metas) > 2 else ""
    episode = " · ".join(meta for meta in metas[3:5] if meta)
    details = " · ".join(meta for meta in metas[5:] if meta)

    if not title:
        return None

    return {
        "title": title,
        "url": urljoin(TV_GUIDE_NEW_TONIGHT_URL, href),
        "image": image,
        "date": date,
        "time": time,
        "network": network,
        "episode": episode,
        "details": details,
        "summary": summary,
    }


def parse_tv_guide_new_tonight(html: str) -> list[dict[str, Any]]:
    """Extract TV Guide's server-rendered New Tonight cards."""

    cards: list[dict[str, Any]] = []
    for fragment in _CARD_SPLIT_RE.split(html or "")[1:]:
        card = _parse_card(f'<div class="c-globalCard {fragment}')
        if card:
            cards.append(card)
    return cards


def fetch_tv_guide_payload(fetcher=None) -> dict[str, Any]:
    """Return TV Guide New Tonight data shaped for the local dark wall view."""

    reader = fetcher or _read_url
    try:
        html = reader(TV_GUIDE_NEW_TONIGHT_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        cards = parse_tv_guide_new_tonight(html)
    except Exception:
        cards = []
    source_name = "TV Guide"
    source_url = TV_GUIDE_NEW_TONIGHT_URL
    if not cards:
        source_name = "TVmaze"
        source_url = "https://www.tvmaze.com/"
        try:
            cards = _fetch_tvmaze_cards(reader)
        except Exception:
            cards = []
    return {
        "ok": bool(cards),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_url": source_url,
        "source_name": source_name,
        "timezone": "America/Chicago",
        "title": "New Tonight",
        "message": (
            "" if cards else "Program data unavailable; capture service is online."
        ),
        "cards": cards[:16],
        "count": len(cards),
    }


def _fetch_tvmaze_cards(reader):
    """Fallback to a dated US schedule, explicitly converted to Central Time."""
    now = datetime.now(ZoneInfo("America/Chicago"))
    date = now.date().isoformat()
    episodes = json.loads(
        reader(
            f"https://api.tvmaze.com/schedule?country=US&date={date}",
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    )
    cards = []
    for episode in episodes:
        show = episode.get("show") or {}
        stamp = episode.get("airstamp")
        if not stamp or not show.get("name"):
            continue
        start = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(
            now.tzinfo
        )
        if start.date() != now.date() or start < now or start.hour < 17:
            continue
        channel = show.get("network") or show.get("webChannel") or {}
        cards.append(
            {
                "title": show["name"],
                "url": episode.get("url") or show.get("url") or "",
                "image": (show.get("image") or {}).get("medium", ""),
                "date": start.strftime("%a %b %d"),
                "time": start.strftime("%I:%M %p %Z"),
                "network": channel.get("name", ""),
                "episode": episode.get("name", ""),
                "details": "US schedule · TVmaze",
                "summary": _clean_html(episode.get("summary") or show.get("summary")),
                "sort_time": start.isoformat(),
            }
        )
    return sorted(cards, key=lambda card: card["sort_time"])
