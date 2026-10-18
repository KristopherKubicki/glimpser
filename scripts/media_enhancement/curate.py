#!/usr/bin/env python3
"""Queue a few coherent clean-history pilots; never change live camera cadence."""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.feed_tv.core import lock, read, write
from scripts.media_enhancement.collect import CAMERAS
from scripts.media_enhancement.queue import ROOT, admission, enqueue
from scripts.media_enhancement.worker import MAX_SOURCE


def select_run(rows, now, minimum=3, maximum=8, prefer_motion=False, ending_at=None):
    """Prefer a recent uninterrupted run with fixed geometry and close captures."""
    groups = []
    current = []
    for row in sorted(rows, key=lambda r: r["captured_at"]):
        if not now - 12 * 3600 <= row["captured_at"] <= now or not row.get("clean"):
            continue
        if current:
            gap = row["captured_at"] - current[-1]["captured_at"]
            if not 0 < gap <= 120 or row["geometry"] != current[-1]["geometry"]:
                groups.append(current)
                current = []
        current.append(row)
    groups.append(current)
    candidates = [
        g[start : start + maximum]
        for g in groups
        for start in range(max(0, len(g) - minimum + 1))
        if len(g[start : start + maximum]) >= minimum
        and (
            ending_at is None
            or g[start : start + maximum][-1]["captured_at"] == ending_at
        )
    ]

    def score(group):
        gaps = [b["captured_at"] - a["captured_at"] for a, b in zip(group, group[1:])]
        # Prefer a tight continuous burst over a longer, sparsely sampled run.
        # Optical flow cannot recover an object's path through a long capture gap.
        if prefer_motion:
            return (
                -max(gaps),
                -sum(gaps) / len(gaps),
                len(group),
                group[-1]["captured_at"],
            )
        return (len(group), group[-1]["captured_at"])

    return max(candidates, key=score, default=[])


def snapshot_run(
    root, camera, now, prefer_motion=False, minimum=3, maximum=8, ending_at=None
):
    """Hold retention's lock through selection and copying; tolerate damaged copies."""
    with lock(root, "collect"):
        rows = []
        for path in (root / "clean-history" / camera).glob("*.json"):
            image = path.with_suffix(".png")
            if path.is_symlink() or image.is_symlink():
                continue
            try:
                row = read(path)
                stamp = row["captured_at"]
                geometry = row["geometry"]
                if (
                    isinstance(stamp, bool)
                    or not isinstance(stamp, (int, float))
                    or not math.isfinite(stamp)
                    or not now - 12 * 3600 <= stamp <= now
                    or not row.get("clean")
                    or row.get("camera") != camera
                    or any(
                        type(geometry[k]) is not int or geometry[k] <= 0
                        for k in ("width", "height")
                    )
                    or geometry.get("duration") != 0
                    or not isinstance(row["source_name"], str)
                    or not isinstance(row["sha256"], str)
                    or not image.is_file()
                ):
                    continue
                row["path"] = image
                rows.append(row)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        # A bad pilot copy must not keep the next healthy run from being selected.
        while rows:
            selected = select_run(
                rows,
                now,
                minimum=minimum,
                maximum=maximum,
                prefer_motion=prefer_motion,
                ending_at=ending_at,
            )
            if not selected:
                break
            payloads, invalid = [], []
            for row in selected:
                try:
                    with row["path"].open("rb") as stream:
                        payload = stream.read(MAX_SOURCE + 1)
                    if (
                        not 0 < len(payload) <= MAX_SOURCE
                        or hashlib.sha256(payload).hexdigest() != row["sha256"]
                    ):
                        raise ValueError("invalid_clean_copy")
                    payloads.append(payload)
                except (OSError, ValueError):
                    invalid.append(row)
            if not invalid:
                return selected, payloads
            rows = [row for row in rows if row not in invalid]
    return [], []


def record_status(root, status):
    # Called under the curate lock: preserve the sibling profile's last result.
    path = root / "curation-status.json"
    previous = read(path)
    profiles = previous.get("profiles", {})
    if previous.get("profile") and not profiles:
        profiles[previous["profile"]] = previous
    profiles[status["profile"]] = status
    write(path, {"checked_at": status["checked_at"], "profiles": profiles})


def camera_order(prior, profile):
    """Give unserved/least recently served cameras the next bounded GPU slot."""
    last = {camera: 0 for camera in CAMERAS}
    for row in prior:
        camera, stamp = row.get("camera"), row.get("queued_at")
        if (
            camera in last
            and row.get("profile") == profile
            and type(stamp) in (int, float)
            and math.isfinite(stamp)
        ):
            last[camera] = max(last[camera], stamp)
    # Stable ties retain the location-interleaved enrollment order.
    return sorted(CAMERAS, key=last.get)


def curate(root=ROOT, now=None, profile="neural-smooth4"):
    now = time.time() if now is None else now
    if profile not in (
        "neural-smooth4",
        "neural-video-2x",
        "neural-2x",
        "neural-native",
        "gentle",
    ):
        raise ValueError("unsupported_pilot_profile")
    still = profile in ("neural-2x", "neural-native", "gentle")
    with lock(root, "curate"):
        prior = [read(p) for p in root.glob("*/job.json")]
        outcomes = {}
        for camera in camera_order(prior, profile):
            # At most one candidate/profile/camera/day, including failed candidates.
            if any(
                r.get("camera") == camera
                and r.get("profile") == profile
                and r.get("queued_at", 0) > now - 86400
                for r in prior
            ):
                outcomes[camera] = "daily_limit"
                continue
            selected, payloads = snapshot_run(
                root,
                camera,
                now,
                prefer_motion=profile.startswith("neural-smooth"),
                minimum=1 if still else 3,
                maximum=1 if still else 8,
            )
            if not selected:
                outcomes[camera] = "no_coherent_run"
                continue
            if still and now - selected[-1]["captured_at"] > 3600:
                outcomes[camera] = "no_recent_still"
                continue
            if profile.startswith("neural-") and any(
                (
                    row["geometry"]["width"]
                    + (0 if still else row["geometry"]["width"] % 2)
                )
                * (
                    row["geometry"]["height"]
                    + (0 if still else row["geometry"]["height"] % 2)
                )
                > (4_200_000 if profile == "neural-native" else 1_050_000)
                for row in selected
            ):
                outcomes[camera] = "native_resolution_exceeds_neural_budget"
                continue
            if (
                profile in {"gentle", "neural-native"}
                and selected[-1]["geometry"]["width"]
                * selected[-1]["geometry"]["height"]
                <= 1_050_000
            ):
                # Small images already have a neural lane; avoid duplicate work.
                outcomes[camera] = "covered_by_neural_profile"
                continue
            try:
                admission(root)
            except ValueError as exc:
                if str(exc) not in ("storage_reserve", "library_full", "queue_full"):
                    raise
                record_status(
                    root,
                    {
                        "checked_at": now,
                        "state": "deferred",
                        "profile": profile,
                        "reason": str(exc),
                        "camera": camera,
                    },
                )
                return None
            with tempfile.TemporaryDirectory(prefix="candidate-", dir=root) as folder:
                if still:
                    source = Path(folder) / "source.png"
                    source.write_bytes(payloads[0])
                else:
                    source = Path(folder) / "source.mp4"
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-nostdin",
                            "-v",
                            "error",
                            "-f",
                            "image2pipe",
                            "-framerate",
                            "2",
                            "-i",
                            "pipe:0",
                            "-an",
                            "-vf",
                            "pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1",
                            "-c:v",
                            "libx264",
                            "-threads",
                            "2",
                            "-crf",
                            "18",
                            "-pix_fmt",
                            "yuv420p",
                            "-y",
                            str(source),
                        ],
                        input=b"".join(payloads),
                        capture_output=True,
                        timeout=40,
                        check=True,
                    )
                stamps = [r["captured_at"] for r in selected]
                job = enqueue(
                    root,
                    source,
                    camera,
                    stamps[-1],
                    profile,
                    "still" if still else "timelapse",
                    None if still else stamps,
                )
                write(
                    root / job / "selection.json",
                    {
                        "source_frames": [r["source_name"] for r in selected],
                        "source_hashes": [r["sha256"] for r in selected],
                        "selected_at": now,
                        "basis": "recent_clean_still"
                        if still
                        else "tight_motion_run"
                        if profile.startswith("neural-smooth")
                        else "close_clean_fixed_geometry",
                        "capture_gaps_seconds": [
                            b - a for a, b in zip(stamps, stamps[1:])
                        ],
                        "review_required": True,
                    },
                )
            record_status(
                root,
                {
                    "checked_at": now,
                    "state": "queued",
                    "id": job,
                    "camera": camera,
                    "profile": profile,
                },
            )
            return job
        record_status(
            root,
            {
                "checked_at": now,
                "state": "no_submission",
                "profile": profile,
                "cameras": outcomes,
            },
        )
    return None


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=[
            "neural-smooth4",
            "neural-video-2x",
            "neural-2x",
            "neural-native",
            "gentle",
        ],
        default="neural-smooth4",
    )
    print(json.dumps({"queued": curate(profile=parser.parse_args().profile)}))
