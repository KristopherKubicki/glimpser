"""Camera capture health reporting utilities."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

from app.viewer_policy import ARCHIVE_GROUPS

SIDECAR_NAMES = {
    "last_caption.png",
    "last_clean.png",
    "last_motion.png",
    "last_motion_caption.png",
    "latest_camera.png",
    "prev_motion.png",
}
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_template_time(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("T", " ").replace("Z", "")):
        try:
            parsed = dt.datetime.strptime(candidate[:19], TIMESTAMP_FORMAT)
            return parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def _age_minutes(value: dt.datetime | None, now: dt.datetime) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return max(0.0, (now - value).total_seconds() / 60.0)


def _canonical_frame_time(camera_name: str, path: Path) -> dt.datetime | None:
    name = path.name
    if name in SIDECAR_NAMES or name.endswith(".orig.png"):
        return None
    prefix = f"{camera_name}_"
    if not name.startswith(prefix) or not name.endswith(".png"):
        return None
    stamp = name[len(prefix) : -4]
    if len(stamp) != 14 or not stamp.isdigit():
        return None
    try:
        parsed = dt.datetime.strptime(stamp, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc)


def _latest_canonical_frame(
    camera_name: str, camera_dir: Path
) -> tuple[Path | None, dt.datetime | None]:
    latest_path = None
    latest_time = None
    if not camera_dir.is_dir():
        return None, None
    for path in camera_dir.glob("*.png"):
        if path.is_symlink():
            continue
        captured_at = _canonical_frame_time(camera_name, path)
        if captured_at is None:
            continue
        if latest_time is None or captured_at > latest_time:
            latest_path = path
            latest_time = captured_at
    return latest_path, latest_time


def _sidecar_state(path: Path) -> dict[str, object]:
    exists = path.exists()
    lexists = os.path.lexists(path)
    is_link = path.is_symlink()
    target = os.path.realpath(path) if is_link else ""
    if not lexists:
        state = "missing"
    elif is_link and not exists:
        state = "broken"
    elif is_link:
        state = "ok"
    else:
        state = "regular"
    return {
        "exists": exists,
        "is_link": is_link,
        "state": state,
        "target": target,
    }


def _latest_video_age_minutes(
    camera_name: str, video_dir: Path, now: dt.datetime
) -> float | None:
    camera_video_dir = video_dir / camera_name
    if not camera_video_dir.is_dir():
        return None
    mtimes = [
        path.stat().st_mtime
        for path in camera_video_dir.glob("*.mp4")
        if path.is_file()
    ]
    if not mtimes:
        return None
    newest = dt.datetime.fromtimestamp(max(mtimes), tz=dt.timezone.utc)
    return _age_minutes(newest, now)


def _groups(details: dict) -> list[str]:
    return [
        group.strip()
        for group in str(details.get("groups") or "").split(",")
        if group.strip()
    ]


def _frequency_minutes(details: dict) -> float:
    try:
        return max(1.0, float(details.get("frequency") or 30))
    except (TypeError, ValueError):
        return 30.0


def _is_private_route_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = parsed.hostname
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host.endswith(".local") or "." not in host


def assess_camera_health(
    name: str,
    details: dict,
    screenshot_dir: str | Path,
    video_dir: str | Path,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    """Return health fields and issue buckets for one camera template."""

    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)

    camera_dir = Path(screenshot_dir) / name
    camera_video_dir = Path(video_dir)
    latest_link = camera_dir / "latest_camera.png"
    latest_state = _sidecar_state(latest_link)
    frame_path, frame_time = _latest_canonical_frame(name, camera_dir)
    db_time = _parse_template_time(details.get("last_screenshot_time"))
    frequency = _frequency_minutes(details)
    stale_after = max(60.0, frequency * 3.0)
    frame_age = _age_minutes(frame_time, now)
    db_age = _age_minutes(db_time, now)
    video_age = _latest_video_age_minutes(name, camera_video_dir, now)
    groups = _groups(details)
    archived = bool(ARCHIVE_GROUPS.intersection(groups))
    expected_offline = "expected-offline" in groups
    last_capture_status = str(details.get("last_capture_status") or "").strip()
    last_capture_message = str(details.get("last_capture_message") or "").strip()

    buckets: list[str] = []
    issues: list[str] = []
    if archived:
        buckets.append("archived_template")
        issues.append("archived/source-stale template")
    if bool(details.get("capture_failed")):
        if not archived:
            buckets.append("capture_failing")
        issues.append("capture_failed=1")
    if str(details.get("offline_since") or "").strip():
        if not archived:
            buckets.append("offline")
        issues.append(f"offline_since={details.get('offline_since')}")
    if last_capture_status == "stale_ok":
        if not archived:
            buckets.append("stale_preserved")
        issue = "last capture preserved previous frame"
        if last_capture_message:
            issue = f"{issue}: {last_capture_message}"
        issues.append(issue)
    if not camera_dir.is_dir():
        if not archived:
            buckets.append("missing_artifacts")
        issues.append("camera directory missing")
    if latest_state["state"] == "missing":
        if not archived:
            buckets.append("missing_latest")
        issues.append("latest_camera.png missing")
    elif latest_state["state"] == "broken":
        if not archived:
            buckets.append("broken_latest")
        issues.append("latest_camera.png broken")
    if frame_path is None:
        if not archived:
            buckets.append("no_frames")
        issues.append("no canonical frames")
    elif frame_age is not None and frame_age > stale_after:
        if not archived:
            buckets.append("stale_frame")
        issues.append(f"latest frame stale ({frame_age:.0f}m)")
    if db_time is None:
        if not archived:
            buckets.append("no_db_capture")
        issues.append("last_screenshot_time empty")
    elif db_age is not None and db_age > stale_after:
        if not archived:
            buckets.append("stale_db_capture")
        issues.append(f"db screenshot time stale ({db_age:.0f}m)")
    if not archived and _is_private_route_url(str(details.get("url") or "")):
        buckets.append("private_route_risk")

    if archived:
        status = "archived"
        severity = -1
    elif expected_offline:
        status = "expected_offline"
        severity = -1
        # Keep raw failure and artifact evidence, but exclude operator-declared
        # outages from actionable buckets and aggregate failure counts.
        buckets = ["operator_expected_offline"]
    elif not issues:
        status = "healthy"
        severity = 0
    elif "capture_failing" in buckets or "broken_latest" in buckets:
        status = "failing"
        severity = 3
    elif "no_frames" in buckets or "missing_latest" in buckets:
        status = "incomplete"
        severity = 2
    else:
        status = "stale"
        severity = 1

    return {
        "name": name,
        "status": status,
        "severity": severity,
        "expected_offline": expected_offline,
        "operator_note": next(
            (
                line
                for line in str(details.get("notes") or "").splitlines()
                if line.startswith("Operator status:")
            ),
            "",
        ),
        "issues": issues,
        "buckets": buckets,
        "groups": groups,
        "frequency_minutes": frequency,
        "stale_after_minutes": stale_after,
        "capture_failed": bool(details.get("capture_failed")),
        "offline_since": str(details.get("offline_since") or ""),
        "last_capture_status": last_capture_status,
        "last_capture_message": last_capture_message,
        "last_capture_status_time": str(details.get("last_capture_status_time") or ""),
        "last_screenshot_time": str(details.get("last_screenshot_time") or ""),
        "last_screenshot_age_minutes": db_age,
        "latest_frame": str(frame_path.name) if frame_path else "",
        "latest_frame_age_minutes": frame_age,
        "latest_camera_state": latest_state["state"],
        "latest_camera_target": latest_state["target"],
        "latest_video_age_minutes": video_age,
        "url": str(details.get("url") or ""),
    }


def build_camera_health_report(
    templates: dict[str, dict],
    screenshot_dir: str | Path,
    video_dir: str | Path,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    """Assess all templates and return a sortable health report."""

    now = now or _utc_now()
    cameras = [
        assess_camera_health(name, details, screenshot_dir, video_dir, now)
        for name, details in templates.items()
    ]
    cameras.sort(
        key=lambda row: (
            -int(row["severity"]),
            (
                row["last_screenshot_age_minutes"]
                if row["last_screenshot_age_minutes"] is not None
                else float("inf")
            ),
            row["name"],
        ),
        reverse=False,
    )

    summary: dict[str, int] = {"total": len(cameras)}
    for row in cameras:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
        for bucket in row["buckets"]:
            summary[bucket] = summary.get(bucket, 0) + 1

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "cameras": cameras,
    }


def format_camera_health_report(
    report: dict[str, object],
    limit: int = 40,
    include_healthy: bool = False,
    include_archived: bool = False,
) -> str:
    """Return a compact operator-readable report."""

    summary = report.get("summary", {})
    lines = [
        f"Camera health report generated {report.get('generated_at')}",
        "Summary: "
        + ", ".join(f"{key}={value}" for key, value in sorted(summary.items())),
        "",
    ]
    cameras = report.get("cameras", [])
    shown = 0
    for row in cameras:
        if not include_healthy and row.get("status") == "healthy":
            continue
        if not include_archived and row.get("status") == "archived":
            continue
        if shown >= limit:
            break
        shown += 1
        age = row.get("last_screenshot_age_minutes")
        age_text = "n/a" if age is None else f"{age:.0f}m"
        frame_age = row.get("latest_frame_age_minutes")
        frame_text = "n/a" if frame_age is None else f"{frame_age:.0f}m"
        groups = ",".join(row.get("groups") or [])
        issues = "; ".join(row.get("issues") or ["route/private only"])
        lines.append(
            f"{shown:02d}. {row.get('name')} [{row.get('status')}] "
            f"db_age={age_text} frame_age={frame_text} "
            f"latest={row.get('latest_camera_state')} groups={groups}"
        )
        lines.append(f"    {issues}")
    if shown == 0:
        lines.append("No camera health issues found.")
    return "\n".join(lines)
