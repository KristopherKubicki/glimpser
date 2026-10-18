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
        rgb.dtype != np.uint8
        or rgb.ndim != 3
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


def prepare_inference(rgb):
    """Lift only model input; do not brighten the evidence or clipped highlights."""
    import numpy as np

    grayscale_metrics(rgb)
    values = rgb.astype(np.float32) / 255
    # A bounded smooth shadow lift gives the model context without a hard knee.
    gain = min(2.0, max(1.0, 0.40 / max(float(values.mean()), 0.01)))
    lifted = values + (gain - 1) * values * (1 - values) ** 2
    return np.rint(lifted * 255).astype(np.uint8), gain


def preserve_luminance(rgb, predicted_bgr):
    """Use inferred chroma only where the saved source has usable signal."""
    import cv2
    import numpy as np

    if predicted_bgr.dtype != np.uint8 or predicted_bgr.shape != rgb.shape:
        raise ValueError("invalid_colorizer_output")
    original = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2Lab)
    inferred = cv2.cvtColor(predicted_bgr.astype(np.float32) / 255, cv2.COLOR_BGR2Lab)
    level = rgb.astype(np.float32).mean(axis=2) / 255
    shadow = np.clip((level - 0.025) / 0.15, 0, 1)
    highlight = np.clip((1 - level) / 0.10, 0, 1)
    confidence = shadow * shadow * (3 - 2 * shadow) * highlight
    inferred[:, :, 0] = original[:, :, 0]
    inferred[:, :, 1:] *= confidence[:, :, None]
    output = np.rint(
        np.clip(cv2.cvtColor(inferred, cv2.COLOR_Lab2RGB), 0, 1) * 255
    ).astype(np.uint8)
    output_l = cv2.cvtColor(output.astype(np.float32) / 255, cv2.COLOR_RGB2Lab)[:, :, 0]
    drift = np.abs(output_l - original[:, :, 0])
    if float(drift.mean()) > 3 or float(np.quantile(drift, 0.99)) > 6:
        raise ValueError("colorizer_luminance_drift")
    return output, float(drift.mean())


def restore(source, target):
    import contextlib

    import numpy as np
    from PIL import Image, ImageOps

    started = time.monotonic()
    with Image.open(source) as image:
        if not 0 < image.width * image.height <= 4_200_000:
            raise ValueError("colorizer_geometry_budget")
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    metrics = grayscale_metrics(rgb)
    inference_rgb, inference_gain = prepare_inference(rgb)
    for name, expected in (
        ("pytorch_model.bin", MODEL_SHA),
        ("config.json", CONFIG_SHA),
    ):
        if hashlib.sha256((MODEL_ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("unexpected_colorizer_weights")
    # The tiny model takes about a second on Spark CPU. Avoid competing with
    # personal LLM GPU reservations; no shared interpreter/package mutations.
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
            inference_rgb[..., ::-1].copy()
        )
    if result.shape != rgb.shape or not np.isfinite(result).all():
        raise ValueError("invalid_colorizer_output")
    output, mean_l_change = preserve_luminance(rgb, result)
    Image.fromarray(output).save(target)
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
        "inference_shadow_gain": round(inference_gain, 4),
        "chroma_signal_gated": True,
        "method": "shadow-aware-colorize-v2",
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
