#!/usr/bin/env python3
"""Describe actual enhancement outcomes and export honest A/B review clips."""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.feed_tv.core import lock, read, write
from scripts.media_enhancement.evaluate import evaluate, video_info
from scripts.media_enhancement.queue import MAX_LIBRARY_BYTES, ROOT
from scripts.media_enhancement.worker import probe


def summarize(row):
    processing = row.get("processing", {})
    timeline = processing.get("timeline", [])
    generated = sum(f.get("type") == "interpolated" for f in timeline)
    slots = [f for f in timeline if "between" in f]
    reasons = Counter(
        f.get("reason", "unknown") for f in slots if f.get("type") == "held"
    )
    motion = row.get("profile", "").startswith("neural-smooth")
    outcome = row.get("state", "unknown")
    if outcome == "ready":
        outcome = (
            ("interpolated" if generated else "no_interpolation")
            if motion
            else "enhanced"
        )
    return {
        "id": row["id"],
        "camera": row["camera"],
        "profile": row["profile"],
        "state": row["state"],
        "outcome": outcome,
        "captured_at": row.get("captured_at"),
        "generated_frames": generated,
        "eligible_slots": len(slots),
        "interpolated_fraction": round(generated / len(slots), 4) if slots else 0,
        "held_reasons": dict(reasons),
        "review_required": True,
        "automatic_rotator_eligible": False,
    }


def report(root=ROOT):
    rows = [summarize(read(p)) for p in sorted(root.glob("*/job.json"))]
    write(
        root / "review-status.json",
        {"jobs": rows, "outcomes": dict(Counter(r["outcome"] for r in rows))},
    )
    return rows


def compare(folder):
    """Use letterboxing, not stretching; labels stay in black gutters."""
    with lock(folder, "comparison"):
        if shutil.disk_usage(folder).free < 15 * 1024**3 + 32 * 1024**2:
            raise RuntimeError("storage_reserve")
        if (
            sum(p.stat().st_size for p in folder.parent.rglob("*") if p.is_file())
            + 32 * 1024**2
            > MAX_LIBRARY_BYTES
        ):
            raise RuntimeError("library_full")
        row = read(folder / "job.json")
        if (
            row.get("state") != "ready"
            or row.get("kind") != "timelapse"
            or row.get("derivative") != "enhanced.mp4"
        ):
            raise ValueError("ready_video_required")
        for name, digest in [
            ("source", row["sha256"]),
            ("enhanced.mp4", row["processing"]["sha256"]),
        ]:
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
                raise ValueError("review_hash_mismatch")
        if row.get("profile") == "neural-temporal-denoise":
            # Diagnostics are evidence only; they never grant display approval.
            write(
                folder / "evaluation.json",
                evaluate(folder / "source", folder / "enhanced.mp4"),
            )
        summary = summarize(row)
        label = (
            "AI interpolated"
            if summary["generated_frames"]
            else "Captured frames held"
            if row["profile"].startswith("neural-smooth")
            else "Neurally enhanced"
        )
        # The actual encoded stream is authoritative, including older jobs
        # whose worker did not include output_fps in processing metadata.
        fps = video_info(folder / "enhanced.mp4")["fps"]
        if not math.isfinite(fps) or not 0 < fps <= 60:
            raise ValueError("invalid_review_fps")
        geometry = f"setpts=PTS-STARTPTS,fps={fps},scale=640:680:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,pad=640:720:(ow-iw)/2:(oh-ih)/2:black"
        filters = f"[0:v]{geometry},drawtext=text='Original captures':x=12:y=8:fontsize=20:fontcolor=white[a];[1:v]{geometry},drawtext=text='{label} - preview':x=12:y=8:fontsize=20:fontcolor=white[b];[a][b]hstack=shortest=1[out]"
        target, temp = folder / "comparison.mp4", folder / "comparison.partial.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(folder / "source"),
                    "-i",
                    str(folder / "enhanced.mp4"),
                    "-filter_complex_threads",
                    "1",
                    "-filter_complex",
                    filters,
                    "-map",
                    "[out]",
                    "-r",
                    str(fps),
                    "-t",
                    str(row["geometry"]["duration"]),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-threads",
                    "2",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-fs",
                    str(32 * 1024**2),
                    "-y",
                    str(temp),
                ],
                capture_output=True,
                timeout=60,
                check=True,
            )
            if not 0 < temp.stat().st_size < 32 * 1024**2:
                raise ValueError("comparison_out_of_budget")
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(temp),
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                timeout=20,
                check=True,
            )
            actual = probe(temp)
            if (
                actual["width"] != 1280
                or actual["height"] != 720
                or abs(actual["duration"] - row["geometry"]["duration"]) > 0.15
            ):
                raise ValueError("comparison_geometry_or_duration")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return target


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    print(compare(args.compare) if args.compare else json.dumps(report()))
