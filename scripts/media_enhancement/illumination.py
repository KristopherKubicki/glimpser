"""Bounded display-lighting recovery after restoration; never invents observations."""

import numpy as np
from PIL import Image, ImageFilter

METHOD = "multiscale-shadow-detail-v2"


def recover_lighting(frame):
    """Lift locally dark areas at native geometry, with noise/highlight gates.

    Three broad illumination scales avoid a single global gamma adjustment.
    A common RGB gain preserves color ratios. No white balance, deglare, clipped
    detail recovery or neural inference is claimed by this deterministic stage.
    """
    source = np.asarray(frame)
    if (
        source.ndim != 3
        or source.shape[2] != 3
        or not 1 <= source.shape[0] * source.shape[1] <= 4_200_000
        or source.dtype != np.uint8
    ):
        raise ValueError("bounded_uint8_rgb_required")
    rgb = source.astype(np.float32) / 255
    y = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    info = {"method": METHOD, "neural": False, "automatic_rotator_eligible": False}
    # Near-black noise contains no recoverable scene detail.
    if float(np.mean(y < 0.025)) >= 0.98:
        return source.copy(), {**info, "state": "held", "reason": "insufficient_signal"}
    if float(np.mean(y < 0.25)) < 0.2:
        return source.copy(), {**info, "state": "held", "reason": "already_lit"}
    plane = Image.fromarray(np.rint(y * 255).astype(np.uint8))
    size = min(source.shape[:2])
    scales = [max(1, size * fraction) for fraction in (0.02, 0.08, 0.20)]
    bases = [
        np.asarray(plane.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
        / 255
        for radius in scales
    ]
    # Geometric averaging limits domination by a bright lamp in a broad window.
    illumination = np.exp(np.mean([np.log(base + 1 / 255) for base in bases], axis=0))
    gain = np.clip((0.38 / illumination) ** 0.45, 1, 2.4)
    signal = np.clip((y - 0.015) / 0.065, 0, 1)
    signal = signal * signal * (3 - 2 * signal)
    shadow = np.clip((0.65 - y) / 0.40, 0, 1)
    highlights = np.clip((0.92 - rgb.max(axis=2)) / 0.22, 0, 1)
    weight = signal * shadow * highlights
    gain = 1 + (gain - 1) * weight
    # Small local-contrast correction is capped and fades at the noise floor.
    detail = np.clip(np.log((y + 1 / 255) / (bases[0] + 1 / 255)), -0.25, 0.25)
    gain *= 1 + 0.12 * detail * weight
    gain = np.minimum(gain, 1 / np.maximum(rgb.max(axis=2), 1 / 255))
    result = np.rint(rgb * gain[..., None] * 255).clip(0, 255).astype(np.uint8)
    # Exact preservation of clipped pixels and near-black readings, including
    # their color ratios. A clipped light cannot be reconstructed by tone mapping.
    protected = (rgb.max(axis=2) >= 0.92) | (y <= 0.015)
    result[protected] = source[protected]
    return result, {
        **info,
        "state": "review_required",
        "maximum_gain": round(float(gain.max()), 4),
        "mean_gain": round(float(gain.mean()), 4),
        "protected_fraction": round(float(protected.mean()), 4),
        "illumination_scales_pixels": scales,
        "median_luma_before": round(float(np.median(y)), 4),
        "median_luma_after": round(
            float(np.median(result @ np.array([0.299, 0.587, 0.114]) / 255)), 4
        ),
    }
