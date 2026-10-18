"""Offline luminance/chroma fusion experiment; no capture or queue side effects."""

import numpy as np
from PIL import Image, ImageFilter


def fuse_channels(frames, *, _exposure_checked=False):
    """Fuse 3–8 aligned RGB captures, anchoring motion and highlights to newest.

    First frame is the current capture. Callers must verify timestamps, camera
    identity and alignment before use; this function cannot infer provenance.
    """
    if not 3 <= len(frames) <= 8:
        raise ValueError("three_to_eight_frames_required")
    current = np.asarray(frames[0], dtype=np.float32)
    if (
        current.ndim != 3
        or current.shape[2] != 3
        or current.shape[0] * current.shape[1] > 1_050_000
    ):
        raise ValueError("bounded_rgb_geometry_required")
    accepted = []
    for frame in frames:
        data = np.asarray(frame, dtype=np.float32)
        if (
            data.shape != current.shape
            or not np.isfinite(data).all()
            or data.min() < 0
            or data.max() > 255
        ):
            raise ValueError("matching_finite_rgb_required")
        if (
            _exposure_checked
            or abs(float(np.median(data)) - float(np.median(current))) <= 12
        ):
            accepted.append(data)
    if len(accepted) < 3:
        return current.astype(np.uint8), {
            "state": "held",
            "reason": "exposure_mismatch",
        }
    stack = np.stack(accepted)
    median = np.median(stack, axis=0)
    changed = np.max(np.abs(current - median), axis=2) > 18
    clipped = np.max(current, axis=2) >= 250
    protected = (
        np.asarray(
            Image.fromarray(((changed | clipped) * 255).astype(np.uint8)).filter(
                ImageFilter.MaxFilter(5)
            )
        )
        > 0
    )
    # Explicit reversible color transform. Median brightness resists outliers;
    # consistent-reference color averaging reduces chroma speckle separately.
    luminance = stack @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    red_difference = stack[..., 0] - luminance
    blue_difference = stack[..., 2] - luminance
    weights = np.max(np.abs(stack - current), axis=3) <= 18
    count = weights.sum(axis=0)
    y = 0.75 * np.median(luminance, axis=0) + 0.25 * luminance[0]
    red = y + (red_difference * weights).sum(axis=0) / count
    blue = y + (blue_difference * weights).sum(axis=0) / count
    green = (y - 0.299 * red - 0.114 * blue) / 0.587
    result = np.stack([red, green, blue], axis=-1)
    result[protected] = current[protected]
    return np.rint(result).clip(0, 255).astype(np.uint8), {
        "state": "review_required",
        "method": "luma-median-chroma-consistent-mean-v1",
        "accepted_frames": len(accepted),
        "protected_fraction": float(protected.mean()),
        "neural": False,
        "automatic_rotator_eligible": False,
    }


def fuse_native_tiles(frames):
    """Fuse up to 4.2 MP at native geometry using bounded overlapping strips.

    Exposure acceptance is measured once over each whole frame. The two-pixel
    halo exactly covers the motion-mask dilation; only strip interiors are kept.
    No resizing, optical-flow warping or interpolated pixels are introduced.
    """
    if not 3 <= len(frames) <= 5:
        raise ValueError("three_to_five_frames_required")
    current = np.asarray(frames[0])
    if (
        current.ndim != 3
        or current.shape[2] != 3
        or not 0 < current.shape[0] * current.shape[1] <= 4_200_000
        or current.dtype != np.uint8
    ):
        raise ValueError("bounded_native_rgb_required")
    accepted = []
    for frame in frames:
        data = np.asarray(frame)
        if data.shape != current.shape or data.dtype != np.uint8:
            raise ValueError("matching_uint8_rgb_required")
        if abs(float(np.median(data)) - float(np.median(current))) <= 12:
            accepted.append(data)
    if len(accepted) < 3:
        raise ValueError("exposure_mismatch")
    height, width = current.shape[:2]
    rows = min(128, 1_050_000 // width - 4)
    if rows < 1:
        raise ValueError("unsupported_strip_width")
    result = np.empty_like(current)
    protected_upper_bound = 0.0
    for start in range(0, height, rows):
        end = min(height, start + rows)
        lo, hi = max(0, start - 2), min(height, end + 2)
        tile, info = fuse_channels([f[lo:hi] for f in accepted], _exposure_checked=True)
        result[start:end] = tile[start - lo : end - lo]
        # Counting overlap twice gives a conservative bound for the existing
        # too-much-motion gate, rather than understating protected area.
        protected_upper_bound += info["protected_fraction"] * (hi - lo) / height
    return result, {
        "state": "review_required",
        "method": "luma-median-chroma-consistent-mean-v1",
        "accepted_frames": len(accepted),
        "protected_fraction": min(1.0, protected_upper_bound),
        "protected_fraction_is_upper_bound": True,
        "native_tiled": True,
        "strip_rows": rows,
        "halo_pixels": 2,
        "neural": False,
        "automatic_rotator_eligible": False,
    }
