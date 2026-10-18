#!/usr/bin/env python3
"""Select bounded multi-frame denoise → personal neural upscale review jobs."""

# Imports below path isolation deliberately follow executable setup.
# ruff: noqa: E402

import hashlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

# Direct invocation puts this directory first, where queue.py shadows stdlib.
sys.path = [
    entry
    for entry in sys.path
    if Path(entry).resolve() != Path(__file__).resolve().parent
]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.utils.screenshots import (
    _estimate_reference_shift,
)
from scripts.feed_tv.core import (
    lock,
    read,
    write,
)
from scripts.media_enhancement.channel_fusion import (
    fuse_channels,
    fuse_native_tiles,
)
from scripts.media_enhancement.collect import (
    CAMERAS,
)
from scripts.media_enhancement.curate import (
    snapshot_run,
)
from scripts.media_enhancement.queue import (
    MAX_SOURCE,
    ROOT,
    enqueue,
)

METHOD = "luma-median-chroma-consistent-mean-v1"


def prepare(payloads, *, native_tiles=False):
    """Reject camera movement before combining same-size, bounded captures."""
    if not 3 <= len(payloads) <= 5 or sum(map(len, payloads)) > MAX_SOURCE:
        raise ValueError("input_budget")
    images = []
    for payload in payloads:
        with Image.open(io.BytesIO(payload)) as image:
            if image.width * image.height > (4_200_000 if native_tiles else 1_050_000):
                raise ValueError("native_resolution_exceeds_neural_budget")
            images.append(image.convert("RGB"))
    current = images[-1]
    for image in images[:-1]:
        if image.size != current.size:
            raise ValueError("geometry_mismatch")
        x, y, score = _estimate_reference_shift(image, current)
        if (x, y) != (0, 0) or not np.isfinite(score) or score < 0.97:
            raise ValueError("alignment_uncertain")
    fusion = fuse_native_tiles if native_tiles else fuse_channels
    result, info = fusion([np.asarray(image) for image in reversed(images)])
    if info["state"] != "review_required":
        raise ValueError("exposure_mismatch")
    if info["protected_fraction"] > 0.35:
        raise ValueError("too_much_changed_area")
    return result, info


def curate_chain(root=ROOT, now=None):
    """Queue at most one chain per run and one per camera/day; keep originals."""
    now = time.time() if now is None else now
    outcomes = {}
    # The worker lock prevents publication before provenance and originals exist.
    with lock(root, "worker"):
        prior = [read(path) for path in root.glob("*/job.json")]
        for camera in CAMERAS:
            if any(
                row.get("camera") == camera
                and row.get("preprocessing", {}).get("method") == METHOD
                and row.get("queued_at", 0) > now - 86400
                for row in prior
            ):
                outcomes[camera] = "daily_limit"
                continue
            rows, payloads = snapshot_run(root, camera, now, minimum=3, maximum=5)
            if not rows:
                outcomes[camera] = "no_coherent_run"
                continue
            try:
                result, info = prepare(payloads)
            except ValueError as exc:
                outcomes[camera] = str(exc)
                continue
            with tempfile.TemporaryDirectory(prefix="chain-", dir=root) as tmp:
                source = Path(tmp) / "fused.png"
                Image.fromarray(result).save(source)
                identifier = enqueue(
                    root, source, camera, rows[-1]["captured_at"], "neural-2x", "still"
                )
                folder = root / identifier
                row = read(folder / "job.json")
                try:
                    for index, payload in enumerate(payloads):
                        (folder / f"capture-{index}.png").write_bytes(payload)
                    row["preprocessing"] = {
                        **info,
                        "capture_times": [item["captured_at"] for item in rows],
                        "source_hashes": [
                            hashlib.sha256(payload).hexdigest() for payload in payloads
                        ],
                        "alignment": "zero_shift_correlation_at_least_0.97",
                    }
                    write(folder / "job.json", row)
                except OSError:
                    row.update(state="failed", reason="chain_provenance_incomplete")
                    write(folder / "job.json", row)
                    raise
            status = {
                "checked_at": now,
                "state": "queued",
                "camera": camera,
                "id": identifier,
                "cameras": outcomes,
            }
            write(root / "chain-status.json", status)
            return status
        status = {"checked_at": now, "state": "no_submission", "cameras": outcomes}
        write(root / "chain-status.json", status)
        return status


if __name__ == "__main__":
    print(json.dumps(curate_chain()))
