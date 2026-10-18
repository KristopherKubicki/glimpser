#!/usr/bin/env python3
"""Explicit opt-in jobs; asynchronous derivatives never replace capture masters."""

# Imports follow path isolation to avoid shadowing the standard library.
# ruff: noqa: E402

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Direct execution must not let this queue.py shadow the standard library.
sys.path = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.feed_tv.core import lock, read, write
from scripts.media_enhancement.worker import (
    MAX_RESULT,
    MAX_SOURCE,
    PROFILES,
    probe,
    recipe_version,
)

ROOT = Path.home() / ".local/share/glimpser-enhancement"
MAX_LIBRARY_BYTES = 4 * 1024**3


def admission(root):
    if shutil.disk_usage(root).free < 15 * 1024**3:
        raise ValueError("storage_reserve")
    if (
        sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        + MAX_SOURCE
        + MAX_RESULT
        > MAX_LIBRARY_BYTES
    ):
        raise ValueError("library_full")
    if (
        sum(
            read(p).get("state") in ("queued", "retry") for p in root.glob("*/job.json")
        )
        >= 20
    ):
        raise ValueError("queue_full")


def enqueue(
    root,
    source,
    camera,
    captured_at,
    profile="gentle",
    kind="still",
    frame_times=None,
    pool=None,
):
    from app.utils.enhancement_pipeline import resolve_pool

    destination = resolve_pool(pool, profile) if pool is not None else None
    if profile not in PROFILES or kind not in ("still", "timelapse"):
        raise ValueError("unsupported_recipe")
    if profile.startswith("neural-"):
        if (
            profile
            in {
                "neural-2x",
                "neural-native",
                "neural-colorize",
                "neural-lowlight",
                "neural-deflare",
                "neural-retinex",
                "neural-cidnet",
                "neural-jpeg",
            }
            and kind != "still"
        ) or (
            profile
            not in {
                "neural-2x",
                "neural-native",
                "neural-colorize",
                "neural-lowlight",
                "neural-deflare",
                "neural-retinex",
                "neural-cidnet",
                "neural-jpeg",
            }
            and kind != "timelapse"
        ):
            raise ValueError("unsupported_neural_media_kind")
    if profile.startswith("neural-") and kind == "timelapse":
        from scripts.media_enhancement.neural import valid_times

        valid_times(
            frame_times, len(frame_times) if isinstance(frame_times, list) else 0
        )
        if abs(frame_times[-1] - captured_at) > 1:
            raise ValueError("capture_end_mismatch")
    if profile == "neural-temporal-denoise":
        from scripts.media_enhancement.restoration_models import adjacent_times

        adjacent_times(frame_times, len(frame_times))
    if not camera or len(camera) > 100 or not 0 < captured_at <= time.time() + 60:
        raise ValueError("invalid_provenance")
    if not 0 < source.stat().st_size <= MAX_SOURCE:
        raise ValueError("source_out_of_budget")
    with source.open("rb") as stream:
        payload = stream.read(MAX_SOURCE + 1)
    if len(payload) > MAX_SOURCE:
        raise ValueError("source_out_of_budget")
    digest = hashlib.sha256(payload).hexdigest()
    identity_parts = [
        digest,
        recipe_version(profile),
        profile,
        kind,
        camera,
        captured_at,
    ]
    if frame_times is not None:
        identity_parts.append(frame_times)
    if pool is not None:
        identity_parts.extend([pool, destination["scope"]])
    identity = json.dumps(identity_parts)
    job_id = hashlib.sha256(identity.encode()).hexdigest()
    with lock(root, "queue"):
        folder = root / job_id
        if (folder / "job.json").exists():
            return job_id
        admission(root)
        # Validate the staged bytes, not a capture file that can change underneath us.
        folder.mkdir(mode=0o700, exist_ok=True)
        try:
            (folder / "source").write_bytes(payload)
            geometry = probe(folder / "source")
            write(
                folder / "job.json",
                {
                    "id": job_id,
                    "state": "queued",
                    "sha256": digest,
                    "version": recipe_version(profile),
                    "frame_times": frame_times,
                    "profile": profile,
                    "kind": kind,
                    "camera": camera,
                    "captured_at": captured_at,
                    "queued_at": time.time(),
                    "geometry": geometry,
                    "attempts": 0,
                    "retry_at": 0,
                    "scope": destination["scope"] if destination else "personal",
                    "pool": pool,
                },
            )
        except Exception:
            shutil.rmtree(folder)
            raise
    return job_id


def supersede_pending(root, camera, pool, profile, captured_at):
    """Retire obsolete pending stills without racing an active worker's manifest.

    The worker owns its lock through inference and the final state write. If it
    is busy, leave all manifests intact; the next dispatch can reconsider them.
    Always reread under the lock rather than saving a dispatcher's old snapshot.
    """
    changed = []
    try:
        with lock(root, "worker"):
            for path in root.glob("*/job.json"):
                if (
                    path.is_symlink()
                    or path.parent.is_symlink()
                    or not re.fullmatch(r"[a-f0-9]{64}", path.parent.name)
                ):
                    continue
                row = read(path)
                if (
                    not isinstance(row, dict)
                    or row.get("id") != path.parent.name
                    or row.get("camera") != camera
                    or row.get("pool") != pool
                    or row.get("profile") != profile
                    or row.get("kind") != "still"
                    or row.get("state") not in {"queued", "retry"}
                    or type(row.get("captured_at")) not in (int, float)
                    or not row["captured_at"] < captured_at
                ):
                    continue
                row.update(state="superseded", reason="newer_capture_available")
                write(path, row)
                changed.append(row["id"])
    except SystemExit as error:
        if error.code != 0:
            raise
    return changed


def run_one(root, executor=None, job_id=None):
    """Drain oldest work, or one explicitly selected private review job."""
    if job_id is not None and not re.fullmatch(r"[a-f0-9]{64}", job_id):
        raise ValueError("invalid_job_id")
    executor = executor or execute
    with lock(root, "worker"):
        jobs = sorted(
            root.glob("*/job.json"), key=lambda p: read(p).get("queued_at", 0)
        )
        for path in jobs:
            if job_id is not None and path.parent.name != job_id:
                continue
            row = read(path)
            if (
                row.get("state") not in ("queued", "retry")
                or row.get("retry_at", 0) > time.time()
            ):
                continue
            if time.time() - row["queued_at"] > 7 * 86400:
                row["state"] = "expired"
                write(path, row)
                continue
            folder = path.parent
            try:
                # Reserve output space too; no automatic deletion of originals.
                if shutil.disk_usage(root).free < 15 * 1024**3 + MAX_RESULT:
                    raise RuntimeError("storage_reserve")
                if (
                    sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
                    + MAX_RESULT
                    > MAX_LIBRARY_BYTES
                ):
                    raise RuntimeError("library_full")
                with (folder / "source").open("rb") as stream:
                    payload = stream.read(MAX_SOURCE + 1)
                if len(payload) > MAX_SOURCE:
                    raise ValueError("source_out_of_budget")
                if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                    raise ValueError("source_hash_mismatch")
                request = {k: row[k] for k in ("version", "profile", "kind", "sha256")}
                request["pool"] = row.get("pool")
                request["scope"] = row.get("scope")
                request["data"] = base64.b64encode(payload).decode()
                request["frame_times"] = row.get("frame_times")
                result = executor(request)
                output = base64.b64decode(result.pop("data"), validate=True)
                if (
                    not 0 < len(output) < MAX_RESULT
                    or hashlib.sha256(output).hexdigest() != result["sha256"]
                ):
                    raise ValueError("invalid_result")
                if (
                    result["recipe"] != row["version"]
                    or result["profile"] != row["profile"]
                ):
                    raise ValueError("wrong_recipe")
                suffix = ".png" if row["kind"] == "still" else ".mp4"
                temp = folder / ("partial" + suffix)
                temp.write_bytes(output)
                actual = probe(temp)
                factor = 2 if row["profile"].endswith("2x") else 1
                expected = [row["geometry"][k] * factor for k in ("width", "height")]
                if row["kind"] == "timelapse":
                    expected = [v + v % 2 for v in expected]
                if [actual["width"], actual["height"]] != expected or abs(
                    actual["duration"] - row["geometry"]["duration"]
                ) > 0.15:
                    raise ValueError("invalid_output_geometry_or_duration")
                if row["kind"] == "timelapse" and row["profile"].startswith("neural-"):
                    validate_video_output(temp, row, result)
                os.replace(temp, folder / ("enhanced" + suffix))
                row.pop("reason", None)
                row.pop("retry_at", None)
                row.update(
                    state="ready",
                    completed_at=time.time(),
                    derivative="enhanced" + suffix,
                    processing=result,
                )
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                subprocess.SubprocessError,
            ) as error:
                busy = "personal_spark_busy_defer" in str(getattr(error, "stderr", ""))
                row["attempts"] += 0 if busy else 1
                row.update(
                    state="failed" if row["attempts"] >= 3 else "retry",
                    retry_at=time.time()
                    + (300 if busy else 900 * 2 ** row["attempts"]),
                    reason="personal_spark_busy" if busy else type(error).__name__,
                )
            finally:
                for temp in folder.glob("partial.*"):
                    temp.unlink(missing_ok=True)
            write(path, row)
            return row["state"]
    return "idle"


def validate_video_output(path, row, result):
    """Verify the encoded frame count, not just an inference worker's claim."""
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    stream = json.loads(process.stdout)["streams"][0]
    count = len(row["frame_times"])
    factor = (
        4
        if row["profile"] == "neural-smooth4"
        else 2
        if row["profile"] == "neural-smooth"
        else 1
    )
    if (
        int(stream["nb_read_frames"]) != count * factor
        or result.get("output_frames") != count * factor
    ):
        raise ValueError("output_frame_count_mismatch")
    timeline = result.get("timeline", [])
    if len(timeline) != count * factor:
        raise ValueError("output_provenance_mismatch")
    for index, stamp in enumerate(row["frame_times"]):
        item = timeline[index * factor]
        if item.get("source_index") != index or item.get("captured_at") != stamp:
            raise ValueError("capture_timeline_mismatch")


def execute(request):
    from app.utils.enhancement_pipeline import resolve_pool

    destination = resolve_pool(request.get("pool") or "default", request["profile"])
    if request.get("scope") != destination["scope"]:
        raise ValueError("enhancement_pool_scope_mismatch")
    result = subprocess.run(
        destination["command"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=240,
        check=True,
    )
    if len(result.stdout) > MAX_RESULT * 4 // 3 + 8192:
        raise ValueError("oversize_response")
    return json.loads(result.stdout)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("enqueue")
    add.add_argument("source", type=Path)
    add.add_argument("--camera", required=True)
    add.add_argument("--captured-at", required=True, type=float)
    add.add_argument("--profile", choices=PROFILES, default="gentle")
    add.add_argument("--kind", choices=("still", "timelapse"), default="still")
    add.add_argument(
        "--frame-times",
        type=Path,
        help="JSON array of original capture timestamps, required for neural smoothing",
    )
    sub.add_parser("run-one")
    args = parser.parse_args()
    if args.action == "enqueue":
        print(
            enqueue(
                args.root,
                args.source,
                args.camera,
                args.captured_at,
                args.profile,
                args.kind,
                json.loads(args.frame_times.read_text()) if args.frame_times else None,
            )
        )
    else:
        print(run_one(args.root))


if __name__ == "__main__":
    main()
