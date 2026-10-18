"""Bounded local diagnostics for frame-preserving video restoration trials.

These measure alterations, not recovered truth or perceptual quality. They never
approve a derivative for display. No downloads, inference or network access.
"""

import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

MAX_FRAMES = 24
MAX_PIXELS = 1_050_000


def video_info(path):
    """Read encoded cadence; reject ambiguous geometry and orientation."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        timeout=15,
    )
    streams = [
        s
        for s in json.loads(result.stdout)["streams"]
        if s.get("codec_type") == "video"
    ]
    if len(streams) != 1:
        raise ValueError("expected_one_video_stream")
    stream = streams[0]
    try:
        fps = float(Fraction(stream["avg_frame_rate"]))
    except (ValueError, ZeroDivisionError, KeyError) as exc:
        raise ValueError("invalid_review_fps") from exc
    if not math.isfinite(fps) or not 0 < fps <= 60:
        raise ValueError("invalid_review_fps")
    if stream.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A", "0:1"):
        raise ValueError("non_square_pixels")
    if stream.get("tags", {}).get("rotate", "0") != "0" or any(
        item.get("rotation", 0) != 0 for item in stream.get("side_data_list", [])
    ):
        raise ValueError("normalize_orientation_first")
    return {"width": stream["width"], "height": stream["height"], "fps": fps}


def decode(path):
    """Decode at most 25 frames; the extra frame detects oversized trials."""
    path = Path(path)
    if path.is_symlink() or not 0 < path.stat().st_size <= 64 * 1024**2:
        raise ValueError("evaluation_source_budget")
    info = video_info(path)
    width, height = info["width"], info["height"]
    if not 4 <= width or not 4 <= height or width * height > MAX_PIXELS:
        raise ValueError("evaluation_geometry_budget")
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-noautorotate",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-frames:v",
            str(MAX_FRAMES + 1),
            "-vsync",
            "0",
            "-threads",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    frame_bytes = width * height * 3
    count, remainder = divmod(len(result.stdout), frame_bytes)
    if remainder or not 5 <= count <= MAX_FRAMES:
        raise ValueError("evaluation_frame_budget")
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(
        count, height, width, 3
    )
    return frames, info


def measure(original, restored):
    """Compare matched samples without resizing, alignment or temporal averaging."""
    if (
        original.shape != restored.shape
        or original.ndim != 4
        or original.shape[-1] != 3
        or not 5 <= len(original) <= MAX_FRAMES
        or original.shape[1] * original.shape[2] > MAX_PIXELS
        or min(original.shape[1:3]) < 4
        or original.dtype != np.uint8
        or restored.dtype != np.uint8
    ):
        raise ValueError("matched_uint8_frames_required")
    # Work frame-by-frame to keep memory independent of clip length.
    changes, shifts, edges, clipping, residual_steps = [], [], [], [], []
    previous_delta = None
    for source, output in zip(original, restored):
        a, b = source.astype(np.float32) / 255, output.astype(np.float32) / 255
        delta = b - a
        changes.append(float(np.abs(delta).mean()))
        shifts.append(float(delta.mean()))
        lumas = [
            x @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32) for x in (a, b)
        ]
        edges.append(
            [
                float(
                    (
                        np.abs(np.diff(x, axis=0)).mean()
                        + np.abs(np.diff(x, axis=1)).mean()
                    )
                    / 2
                )
                for x in lumas
            ]
        )
        clipping.append([float((x.max(axis=2) >= 254 / 255).mean()) for x in (a, b)])
        if previous_delta is not None:
            residual_steps.append(float(np.abs(delta - previous_delta).mean()))
        previous_delta = delta
    edge_a, edge_b = np.mean(edges, axis=0)
    return {
        "schema": "restoration-diagnostics-v1",
        "frames": len(original),
        "width": original.shape[2],
        "height": original.shape[1],
        "mean_absolute_change": float(np.mean(changes)),
        "mean_brightness_shift": float(np.mean(shifts)),
        "brightness_shift_std": float(np.std(shifts)),
        "fixed_pixel_residual_change": float(np.mean(residual_steps)),
        "edge_energy_ratio": float(edge_b / edge_a) if edge_a > 1e-6 else None,
        "clipped_fraction_change": float(
            np.mean(clipping, axis=0)[1] - np.mean(clipping, axis=0)[0]
        ),
        "review_required": True,
        "automatic_rotator_eligible": False,
        "limitations": "No clean reference. Edge loss can be denoising or lost detail. Residual variation can be motion, noise, or flicker; it is not motion-compensated. Visual review required.",
    }


def evaluate(source, derivative):
    """Evaluate exact-size, exact-count, equal-cadence clips with file hashes."""
    a, ai = decode(source)
    b, bi = decode(derivative)
    if abs(ai["fps"] - bi["fps"]) > 0.001:
        raise ValueError("evaluation_cadence_mismatch")
    report = measure(a, b)
    report.update(
        fps=ai["fps"],
        source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        derivative_sha256=hashlib.sha256(Path(derivative).read_bytes()).hexdigest(),
    )
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("derivative", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.source, args.derivative), indent=2, allow_nan=False))
