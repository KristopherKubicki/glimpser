"""Private, offline night snapshot fusion; never changes capture or display policy."""

import argparse
import hashlib
import io
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from scripts.media_enhancement.chain import prepare
from scripts.media_enhancement.curate import snapshot_run
from scripts.media_enhancement.illumination import recover_lighting
from scripts.media_enhancement.queue import ROOT


def preview(rows, payloads, camera, now):
    """Verify original provenance, then fuse aligned snapshots and lift shadows.

    Sparse captures are not adjacent video frames. Geometry and correlation
    checks reject uncertain alignment; this is a review experiment, not proof
    that all scene changes have been detected.
    """
    if not 3 <= len(rows) <= 5 or len(rows) != len(payloads):
        raise ValueError("three_to_five_captures_required")
    stamps = []
    for row, payload in zip(rows, payloads):
        stamp = row.get("captured_at")
        if (
            row.get("camera") != camera
            or row.get("clean") is not True
            or type(stamp) not in (int, float)
            or not math.isfinite(stamp)
            or not now - 12 * 3600 <= stamp <= now
            or hashlib.sha256(payload).hexdigest() != row.get("sha256")
        ):
            raise ValueError("invalid_capture_provenance")
        stamps.append(stamp)
    if any(not 0 < b - a <= 120 for a, b in zip(stamps, stamps[1:])):
        raise ValueError("capture_gap_or_order")
    fused, fusion = prepare(payloads, native_tiles=True)
    with Image.open(io.BytesIO(payloads[-1])) as image:
        current = np.asarray(image.convert("RGB"))
    # Sparse-frame motion masks have hard boundaries, particularly on clouds.
    # Fade fusion to the current capture around every disagreement, without
    # blurring the image itself or borrowing detail inside a protected region.
    disagreement = np.zeros(current.shape[:2], dtype=bool)
    for payload in payloads[:-1]:
        with Image.open(io.BytesIO(payload)) as image:
            reference = np.asarray(image.convert("RGB"), dtype=np.int16)
        disagreement |= (
            np.max(np.abs(reference - current.astype(np.int16)), axis=2) > 12
        )
    mask = Image.fromarray((disagreement * 255).astype(np.uint8)).filter(
        ImageFilter.MaxFilter(5)
    )
    halo = np.asarray(mask.filter(ImageFilter.GaussianBlur(4)), dtype=np.float32) / 255
    weight = 1 - np.maximum(halo, np.asarray(mask, dtype=np.float32) / 255)
    fused = (
        np.rint(
            current.astype(np.float32)
            + weight[..., None] * (fused.astype(np.float32) - current)
        )
        .clip(0, 255)
        .astype(np.uint8)
    )
    # A bright daytime scene should not enter a night experiment merely because
    # a small patch contains shadows.
    if float(np.median(current)) > 90:
        raise ValueError("not_low_light")
    enhanced, lighting = recover_lighting(fused)
    return enhanced, {
        "state": "review_required",
        "method": "aligned-night-snapshot-fusion-shadow-lift-v1",
        "badge": "Multiframe denoise · shadow lift · experimental",
        "camera": camera,
        "captured_at": stamps[-1],
        "capture_times": stamps,
        "source_hashes": [row["sha256"] for row in rows],
        "fusion": fusion,
        "fusion_preserved_current_fraction": float(np.mean(weight == 0)),
        "lighting": lighting,
        "neural": False,
        "color_inferred": False,
        "automatic_rotator_eligible": False,
        "alert_source_eligible": False,
    }


def main():
    """Write one private review bundle without enqueueing or overwriting files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        not args.camera
        or Path(args.camera).name != args.camera
        or args.camera in {".", ".."}
    ):
        parser.error("camera must be one directory name")
    now = time.time()
    rows, payloads = snapshot_run(args.root, args.camera, now, maximum=5)
    enhanced, report = preview(rows, payloads, args.camera, now)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for index, payload in enumerate(payloads):
        (args.output / f"source-{index}.png").write_bytes(payload)
    Image.fromarray(enhanced).save(args.output / "enhanced.png")
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
