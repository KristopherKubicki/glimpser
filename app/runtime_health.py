"""Bounded, read-only capability and capture-health checks."""

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.encoder_pipe import run_encoder_command
from app.gpu_guard import gpu_fault
from app.viewer_policy import ARCHIVE_GROUPS

BEACH_EUFY_MAX_AGE_SECONDS = 16 * 60 * 60


def probe_acceleration(ffmpeg_path: str, method: str) -> dict:
    """Verify CUDA encoding with a synthetic frame; never contact a source."""
    selected = str(method or "false").lower()
    result = {"requested": selected, "effective": selected, "status": "unverified"}
    if selected in {"false", "none", "off", ""}:
        return {**result, "effective": "false", "status": "disabled"}
    if selected != "cuda":
        return result
    fault = gpu_fault()
    if fault:
        return {
            **result,
            "effective": "false",
            "status": "failed",
            "reason": fault["reason"],
        }
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=128x128:r=1",
        "-frames:v",
        "1",
        "-c:v",
        "h264_nvenc",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = run_encoder_command(command, timeout=8)
        if completed.returncode == 0:
            return {**result, "status": "verified"}
        reason = "CUDA encoder initialization failed"
    except subprocess.TimeoutExpired:
        reason = "CUDA encoder probe timed out"
    except OSError:
        reason = "FFmpeg could not be executed"
    return {**result, "effective": "false", "status": "failed", "reason": reason}


def capture_health(database_path: str, now: datetime | None = None) -> dict:
    """Summarize persisted capture freshness, without scanning media directories.

    This deliberately reports database telemetry, not playable-frame integrity.
    Freshness allows three intervals or one hour, except the daylight-only
    Beach Eufy sweep, whose bridge permits a 16-hour overnight gap.
    """
    now = now or datetime.now(UTC)
    summary = dict(
        total=0, active=0, archived=0, expected_offline=0, failed=0, stale=0, fresh=0
    )
    uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        rows = connection.execute(
            "SELECT frequency, last_screenshot_time, capture_failed, groups FROM templates"
        ).fetchall()
    finally:
        connection.close()
    for frequency, last_capture, failed, groups in rows:
        summary["total"] += 1
        group_names = {part.strip().lower() for part in (groups or "").split(",")}
        if ARCHIVE_GROUPS.intersection(group_names):
            summary["archived"] += 1
            continue
        if "expected-offline" in group_names:
            summary["expected_offline"] += 1
            continue
        summary["active"] += 1
        if failed:
            summary["failed"] += 1
            continue
        try:
            stamp = datetime.fromisoformat(last_capture.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            limit = max(60, float(frequency or 30) * 3) * 60
            if {"beachhouse", "eufy"}.issubset(group_names):
                # The external Eufy sweep intentionally pauses overnight.
                limit = max(limit, BEACH_EUFY_MAX_AGE_SECONDS)
            stale = (now - stamp).total_seconds() > limit
        except (AttributeError, TypeError, ValueError):
            stale = True
        summary["stale" if stale else "fresh"] += 1
    return {"basis": "database_capture_telemetry", **summary}
