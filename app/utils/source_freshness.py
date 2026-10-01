"""Source-age evidence, kept separately from the time Glimpser took a screenshot."""

import hashlib
import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from app import config


def timestamp(value):
    """Parse stored UTC timestamps without guessing an image's printed date."""
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return (
            parsed.replace(tzinfo=timezone.utc)
            if not parsed.tzinfo
            else parsed.astimezone(timezone.utc)
        )
    except (ValueError, TypeError):
        return None


def _path(name):
    # Hash names instead of trusting a template name as a filesystem path.
    key = hashlib.sha256(str(name).encode()).hexdigest()
    return (
        Path(config.DATABASE_PATH).resolve().parent / "source_freshness" / f"{key}.json"
    )


def read_evidence(name):
    """Read best-effort evidence; a missing/corrupt record means unknown."""
    try:
        value = json.loads(_path(name).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def record_source(
    name,
    identity,
    *,
    digest="",
    modified="",
    inherited="",
    capture_file="",
    frame_condition=None,
    now=None,
):
    """Persist a validated source observation without recording URLs or credentials.

    First-seen time is only a lower bound on image age. HTTP Last-Modified is
    publisher metadata, not proof that a camera exposed a frame at that time.
    """
    now = now or datetime.now(timezone.utc)
    observed = now.isoformat()
    key = hashlib.sha256(str(identity).encode()).hexdigest()
    prior = read_evidence(name)
    same = bool(
        digest and prior.get("identity") == key and prior.get("digest") == digest
    )
    published = None
    try:
        published = parsedate_to_datetime(modified) if modified else None
        if published and not published.tzinfo:
            published = published.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        pass
    try:
        observations = max(0, int(prior.get("observations", 0)))
    except (ValueError, TypeError, OverflowError):
        observations = 0
    value = {
        "identity": key,
        "capture_file": capture_file or (prior.get("capture_file", "") if same else ""),
        "digest": digest,
        "first_seen": prior.get("first_seen", observed) if same else observed,
        "checked_at": observed,
        "published_at": (
            published.isoformat()
            if published
            else (prior.get("published_at", "") if same else "")
        ),
        "inherited_at": inherited,
        "frame_condition": (
            frame_condition
            if frame_condition is not None
            else (prior.get("frame_condition", "") if same else "")
        ),
        "observations": min(observations + 1, 1000000) if same else 1,
    }
    path = _path(name)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle)
        temporary.replace(path)
    except OSError:
        logging.warning("Could not persist source-age evidence for %s", name)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def record_derived_source(name, parent, source_file, output_file):
    """Preserve age through crops/composites, binding ancestry to the exact file."""
    match = re.fullmatch(
        re.escape(parent) + r"_(\d{14})(?:_blank)?\.png", Path(source_file).name
    )
    if not match:
        return
    try:
        captured = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return
    parent_evidence = read_evidence(parent)
    published = None
    frame_condition = ""
    if parent_evidence.get("capture_file") == Path(source_file).name:
        # Do not borrow a newer parent's metadata for an older archived frame.
        ancestor = timestamp(parent_evidence.get("inherited_at"))
        if ancestor and ancestor < captured:
            captured = ancestor
        published = timestamp(parent_evidence.get("published_at"))
        frame_condition = parent_evidence.get("frame_condition", "")
    record_source(
        name,
        parent,
        inherited=captured.isoformat(),
        modified=published.strftime("%a, %d %b %Y %H:%M:%S GMT") if published else "",
        capture_file=Path(output_file).name,
        frame_condition=frame_condition,
    )


def source_freshness(name, details, now=None):
    """Project only safe age evidence for the current camera configuration."""
    now = now or datetime.now(timezone.utc)
    evidence = read_evidence(name)
    identity = details.get("source_template") or details.get("url") or ""
    if evidence.get("identity") != hashlib.sha256(str(identity).encode()).hexdigest():
        evidence = {}
    try:
        threshold = max(
            1800, min(720, max(1, int(details.get("frequency") or 30))) * 180
        )
    except (TypeError, ValueError, OverflowError):
        threshold = 5400
    # Never attach a newer observation to an older displayed image (or vice
    # versa). Capture filenames are the binding, not the record write time.
    filename = str(evidence.get("capture_file") or "")
    captured = timestamp(details.get("last_screenshot_time"))
    if filename and captured:
        match = re.fullmatch(
            re.escape(str(name)) + r"_(\d{14})(?:_blank)?\.png", filename
        )
        if match:
            try:
                file_time = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(
                    tzinfo=timezone.utc
                )
                if abs((file_time - captured).total_seconds()) > 1:
                    evidence = {}
            except ValueError:
                evidence = {}
        else:
            evidence = {}
    published = timestamp(evidence.get("published_at"))
    inherited = timestamp(evidence.get("inherited_at"))
    first = timestamp(evidence.get("first_seen"))
    known = published or inherited
    source_older = bool(known and (now - known).total_seconds() > threshold)
    try:
        observations = int(evidence.get("observations", 0))
    except (TypeError, ValueError, OverflowError):
        observations = 0
    checked = timestamp(evidence.get("checked_at"))
    # A disconnected kiosk must not accumulate observations that never happened.
    observed_seconds = (checked - first).total_seconds() if checked and first else 0
    unchanged = bool(
        first
        and checked
        and checked <= now
        and observations > 1
        and observed_seconds > threshold
    )
    capture_overdue = bool(captured and (now - captured).total_seconds() > threshold)
    reason = str(details.get("last_capture_message") or "")
    return {
        "capture_overdue": capture_overdue,
        "last_attempt_at": str(details.get("last_capture_status_time") or ""),
        "waiting_for_browser": reason == "stale_previous_frame_browser_slot_busy",
        "source_unchanged": reason == "source_checked_unchanged",
        "checked_at": str(evidence.get("checked_at") or ""),
        "kind": (
            "video_thumbnail"
            if (urlparse(str(details.get("url") or "")).hostname or "").lower()
            in {"i.ytimg.com", "img.youtube.com"}
            else ""
        ),
        "published_at": published.isoformat() if published else "",
        "inherited_at": inherited.isoformat() if inherited else "",
        "unchanged_since": first.isoformat() if unchanged else "",
        "unchanged_seconds": int(observed_seconds) if unchanged else 0,
        "low_light": evidence.get("frame_condition") == "low_light",
        "retained": details.get("last_capture_status") == "stale_ok",
        "older": source_older,
        "clock_ahead": bool(known and (known - now).total_seconds() > 300),
        "threshold_seconds": threshold,
    }
