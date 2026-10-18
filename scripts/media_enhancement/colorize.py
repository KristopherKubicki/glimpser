#!/usr/bin/env python3
"""Private DDColor inference. Inferred chroma never replaces source evidence."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

MODEL_ROOT = Path.home() / ".local/lib/glimpser-colorizer"
MODEL_SHA = "8a1277bc90a1bfbb6d2d83933a9a6bc821931879ca93e26e4fcec12165d41fce"  # pragma: allowlist secret -- pinned public model/code checksum
CONFIG_SHA = "9be44eebc1e7043d02d0f9ef66552f16bef04904e9c96b8c2fc82b3a2243d0de"  # pragma: allowlist secret -- pinned public model/code checksum
CODE_REVISION = "2adb63f2656ac41cbdf7b894cddd94121a3faf13"  # pragma: allowlist secret -- pinned public model/code checksum


def grayscale_metrics(rgb):
    import numpy as np

    if (
        rgb.ndim != 3
        or rgb.shape[2] != 3
        or not 0 < rgb.shape[0] * rgb.shape[1] <= 4_200_000
    ):
        raise ValueError("colorizer_geometry_budget")
    delta = np.max(rgb, axis=2).astype(float) - np.min(rgb, axis=2)
    if float(np.quantile(delta, 0.95)) > 3:
        raise ValueError("original_already_has_color")
    if float(rgb.mean()) < 45:
        raise ValueError("colorizer_insufficient_visible_light")
    return {"channel_difference_p95": float(np.quantile(delta, 0.95))}


def restore(source, target):
    import contextlib

    import numpy as np
    from PIL import Image, ImageOps

    started = time.monotonic()
    with Image.open(source) as image:
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    metrics = grayscale_metrics(rgb)
    for name, expected in (
        ("pytorch_model.bin", MODEL_SHA),
        ("config.json", CONFIG_SHA),
    ):
        if hashlib.sha256((MODEL_ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("unexpected_colorizer_weights")
    # The tiny model takes about a second on Spark CPU. Avoid competing with
    # personal LLM GPU reservations; no shared interpreter/package mutations.
    import cv2
    import torch

    torch.set_num_threads(2)
    sys.path.insert(0, str(MODEL_ROOT / "DDColor"))
    with contextlib.redirect_stdout(sys.stderr):
        from ddcolor import ColorizationPipeline, DDColor

        config = json.loads((MODEL_ROOT / "config.json").read_text())
        config["input_size"] = [256, 256]
        model = DDColor(**config)
        model.load_state_dict(
            torch.load(
                MODEL_ROOT / "pytorch_model.bin", map_location="cpu", weights_only=True
            ),
            strict=True,
        )
        model.eval()
        result = ColorizationPipeline(model, input_size=256, device="cpu").process(
            rgb[..., ::-1].copy()
        )
    if result.shape != rgb.shape or not np.isfinite(result).all():
        raise ValueError("invalid_colorizer_output")
    # Colorization must preserve scene geometry and luminance; no invented detail.
    original_l = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2Lab)[:, :, 0]
    result_l = cv2.cvtColor(result.astype(np.float32) / 255, cv2.COLOR_BGR2Lab)[:, :, 0]
    mean_l_change = float(np.abs(result_l - original_l).mean())
    if mean_l_change > 3:
        raise ValueError("colorizer_luminance_drift")
    Image.fromarray(result[..., ::-1]).save(target)
    return {
        "backend": "personal-spark-cpu-pytorch",
        "neural": True,
        "generative": True,
        "color_inferred": True,
        "reference_guided": False,
        "model": "DDColor paper tiny",
        "model_sha256": MODEL_SHA,
        "model_code_revision": CODE_REVISION,
        "source_luminance_preserved": True,
        "mean_luminance_change": round(mean_l_change, 4),
        "synthetic_frames": 0,
        "face_restoration": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        **metrics,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.source, args.target)))


if __name__ == "__main__":
    main()
