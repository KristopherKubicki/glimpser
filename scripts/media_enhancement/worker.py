#!/usr/bin/env python3
"""Bounded classical and opt-in neural derivatives on the personal Spark."""

import base64
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "spatial-v1"
MAX_SOURCE = 32 * 1024**2
MAX_RESULT = 64 * 1024**2
PROFILES = {
    # Explicit zero temporal strength: timelapse frames can be minutes apart.
    "gentle": "hqdn3d=1.2:0.9:0:0",
    "gentle-2x": "hqdn3d=1.2:0.9:0:0,scale=iw*2:ih*2:flags=lanczos",
    "neural-2x": None,
    "neural-native": None,
    "neural-colorize": None,
    "neural-deflare": None,
    "neural-retinex": None,
    "neural-cidnet": None,
    "neural-jpeg": None,
    "neural-temporal-denoise": None,
    "neural-lowlight": None,
    "neural-smooth": None,
    "neural-smooth4": None,
    "neural-video-2x": None,
}


def recipe_version(profile):
    if profile == "neural-colorize":
        return "neural-colorize-v2"
    if profile in {
        "neural-retinex",
        "neural-cidnet",
        "neural-jpeg",
        "neural-temporal-denoise",
    }:
        return profile + "-v1"
    if profile == "neural-deflare":
        return "neural-deflare-v1"
    if profile == "neural-lowlight":
        return "neural-lowlight-v1"
    if profile == "neural-native":
        return "neural-native-v1"
    if profile in ("neural-smooth", "neural-smooth4", "neural-video-2x"):
        return "neural-v2"
    return "neural-v1" if profile == "neural-2x" else VERSION


def probe(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=15,
        check=True,
    )
    data = json.loads(result.stdout)
    videos = [s for s in data["streams"] if s["codec_type"] == "video"]
    if len(videos) != 1:
        raise ValueError("expected_one_video_stream")
    stream = videos[0]
    width, height = stream["width"], stream["height"]
    if not 1 <= width * height <= 4_200_000:
        raise ValueError("source_dimensions_out_of_budget")
    if stream.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A", "0:1"):
        raise ValueError("normalize_pixel_aspect_before_enhancement")
    if stream.get("tags", {}).get("rotate", "0") != "0" or any(
        s.get("rotation", 0) != 0 for s in stream.get("side_data_list", [])
    ):
        raise ValueError("normalize_orientation_before_enhancement")
    duration = float(data.get("format", {}).get("duration", 0))
    if not 0 <= duration <= 30:
        raise ValueError("duration_out_of_budget")
    return {"width": width, "height": height, "duration": duration}


def restore(source, target, profile, kind, frame_times=None):
    started = time.monotonic()
    if profile not in PROFILES or kind not in ("still", "timelapse"):
        raise ValueError("unsupported_recipe")
    before = probe(source)
    if kind == "timelapse" and before["duration"] <= 0:
        raise ValueError("missing_duration")
    if profile.endswith("2x") and before["width"] * before["height"] > 1_050_000:
        raise ValueError("upscale_dimensions_out_of_budget")
    neural_result = {}
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
        command = [
            "/opt/spark-media/.venv/bin/python",
            str(Path(__file__).with_name("neural.py")),
            str(source),
            str(target),
            profile,
        ]
        if profile == "neural-colorize":
            command = [
                command[0],
                str(Path(__file__).with_name("colorize.py")),
                str(source),
                str(target),
            ]
        if kind == "timelapse":
            times = target.with_suffix(".times.json")
            times.write_text(json.dumps(frame_times))
            command += ["--times", str(times)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if process.returncode:
            if "personal_spark_busy_defer" in process.stderr:
                raise RuntimeError("personal_spark_busy_defer:gpu")
            raise RuntimeError("neural_worker_failed")
        neural_result = json.loads(process.stdout)
    else:
        command = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-threads",
            "2",
            "-noautorotate",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-map_metadata",
            "-1",
            "-filter_threads",
            "2",
            "-vf",
            PROFILES[profile] + ",setsar=1",
        ]
        if kind == "still":
            command += ["-frames:v", "1", "-c:v", "png"]
        else:
            # Pad odd dimensions; never stretch to make an encoder accept a frame.
            command[-1] += ",pad=ceil(iw/2)*2:ceil(ih/2)*2"
            command += [
                "-t",
                "30",
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ]
        command += ["-fs", str(MAX_RESULT), "-y", str(target)]
        subprocess.run(command, capture_output=True, timeout=180, check=True)
    after = probe(target)
    factor = 2 if profile.endswith("2x") else 1
    expected = [before[k] * factor for k in ("width", "height")]
    if kind == "timelapse":
        expected = [v + v % 2 for v in expected]
    if [after["width"], after["height"]] != expected:
        raise ValueError("geometry_mismatch")
    if kind == "timelapse" and abs(after["duration"] - before["duration"]) > 0.15:
        raise ValueError("incomplete_derivative")
    if not 0 < target.stat().st_size < MAX_RESULT:
        raise ValueError("output_out_of_budget")
    return {
        "before": before,
        "after": after,
        "backend": "personal-spark-cpu-ffmpeg",
        "recipe": recipe_version(profile),
        "profile": profile,
        "generative": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        **neural_result,
    }


def capacity():
    memory = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    if int(memory["MemAvailable"].split()[0]) < 10 * 1024**2 or os.getloadavg()[0] > (
        os.cpu_count() or 1
    ):
        raise RuntimeError("personal_spark_busy_defer:host_capacity")


def main():
    root = Path.home() / ".cache/glimpser-enhancement"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("personal_spark_busy_defer:worker_lock") from None
        capacity()
        if shutil.disk_usage(root).free < 15 * 1024**3:
            raise RuntimeError("personal_spark_busy_defer:disk_reserve")
        request = json.loads(sys.stdin.buffer.read(MAX_SOURCE * 4 // 3 + 8192))
        if request.get("version") != recipe_version(request.get("profile", "")):
            raise ValueError("recipe_version_mismatch")
        payload = base64.b64decode(request["data"], validate=True)
        if not 0 < len(payload) <= MAX_SOURCE:
            raise ValueError("source_out_of_budget")
        if hashlib.sha256(payload).hexdigest() != request["sha256"]:
            raise ValueError("source_hash_mismatch")
        kind = request["kind"]
        with tempfile.TemporaryDirectory(dir=root) as folder:
            source = Path(folder) / "source"
            target = Path(folder) / (
                "enhanced.png" if kind == "still" else "enhanced.mp4"
            )
            source.write_bytes(payload)
            result = restore(
                source, target, request["profile"], kind, request.get("frame_times")
            )
            output = target.read_bytes()
            result.update(
                data=base64.b64encode(output).decode(),
                sha256=hashlib.sha256(output).hexdigest(),
            )
            print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No source paths, camera URLs, payloads or subprocess arguments in logs.
        print(
            str(error)
            if str(error)
            in {
                "personal_spark_busy_defer",
                "personal_spark_busy_defer:gpu",
                "personal_spark_busy_defer:host_capacity",
                "personal_spark_busy_defer:worker_lock",
                "personal_spark_busy_defer:disk_reserve",
            }
            else type(error).__name__,
            file=sys.stderr,
        )
        sys.exit(1)
