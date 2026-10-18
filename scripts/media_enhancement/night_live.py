"""Bounded local night recipe, using exact-capture provenance and normal publishing."""

import hashlib
import io
import json
import time

import numpy as np
from PIL import Image

from app.utils.enhancement_pipeline import resolve_pool
from scripts.feed_tv.core import lock, write
from scripts.media_enhancement.curate import snapshot_run
from scripts.media_enhancement.illumination import recover_lighting
from scripts.media_enhancement.night_preview import preview
from scripts.media_enhancement.queue import MAX_RESULT, MAX_SOURCE, admission

VERSION = "night-adaptive-v3"


def produce(root, source, camera, stamp, pool, now=None, *, max_age=900):
    """Make a ready native-size derivative; uncertainty falls back to one frame.

    This CPU recipe runs on the capture guest, not the GPU executor. It never
    contacts a camera. Publication still requires the current source hash and
    explicit camera display opt-in through the normal integration path.
    """
    now = time.time() if now is None else now
    destination = resolve_pool(pool, "night-adaptive")
    if not 0 <= now - stamp <= min(3600, max_age):
        raise ValueError("stale_source")
    with source.open("rb") as stream:
        payload = stream.read(MAX_SOURCE + 1)
    if not 0 < len(payload) <= MAX_SOURCE:
        raise ValueError("source_out_of_budget")
    digest = hashlib.sha256(payload).hexdigest()
    with Image.open(io.BytesIO(payload)) as image:
        if not 0 < image.width * image.height <= 4_200_000:
            raise ValueError("recipe_pixel_budget")
        current = np.array(image.convert("RGB"))
    result, lighting = recover_lighting(current)
    mode, reason, provenance, originals = "single-frame", "no_matching_history", {}, []
    # Bright captures stay original and do not consume library space or receive
    # a badge suggesting they were improved.
    if lighting["state"] == "held":
        return None
    rows, payloads = snapshot_run(root, camera, now, maximum=5, ending_at=stamp)
    if rows and rows[-1]["sha256"] == digest:
        try:
            result, provenance = preview(rows, payloads, camera, now)
            lighting = provenance["lighting"]
            mode, reason, originals = "multiframe", None, payloads
        except ValueError as exc:
            reason = str(exc)
    encoded = io.BytesIO()
    Image.fromarray(result).save(encoded, format="PNG")
    output = encoded.getvalue()
    if len(output) > MAX_RESULT:
        raise ValueError("result_out_of_budget")
    identity = [VERSION, camera, stamp, digest, pool, destination["scope"]]
    identifier = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    geometry = {"width": current.shape[1], "height": current.shape[0], "duration": 0.0}
    with lock(root, "queue"):
        folder = root / identifier
        if (folder / "job.json").exists():
            return identifier
        admission(root)
        # Admission reserves 96 MiB; all bytes of this local bundle must fit it.
        if (
            len(payload) + len(output) + sum(map(len, originals))
            > MAX_SOURCE + MAX_RESULT
        ):
            raise ValueError("bundle_out_of_budget")
        folder.mkdir(mode=0o700, exist_ok=True)
        (folder / "source").write_bytes(payload)
        (folder / "enhanced.png").write_bytes(output)
        for index, original in enumerate(originals):
            (folder / f"capture-{index}.png").write_bytes(original)
        write(
            folder / "job.json",
            {
                "id": identifier,
                "state": "ready",
                "sha256": digest,
                "version": VERSION,
                "profile": "night-adaptive",
                "kind": "still",
                "camera": camera,
                "captured_at": stamp,
                "queued_at": now,
                "completed_at": now,
                "pool": pool,
                "scope": destination["scope"],
                "geometry": geometry,
                "derivative": "enhanced.png",
                "processing": {
                    "recipe": VERSION,
                    "profile": "night-adaptive",
                    "mode": mode,
                    "fallback_reason": reason,
                    "lighting": lighting,
                    "before": geometry,
                    "after": geometry,
                    "sha256": hashlib.sha256(output).hexdigest(),
                    "neural": False,
                    "color_inferred": False,
                    "review_only": False,
                    "night_provenance": provenance,
                },
            },
        )
    return identifier
