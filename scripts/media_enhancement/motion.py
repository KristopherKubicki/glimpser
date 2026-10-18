"""Geometry-preserving forward splatting for neural flow interpolation.

RAFT predicts displacement at a source pixel. Forward splatting places that
pixel at its actual intermediate destination; sampling a source with negative
flow at the target coordinate is not equivalent for spatially varying motion.
"""

import numpy as np


def splat_midpoint(first, second, forward, backward, alpha, confidence=None):
    if not 0 <= alpha <= 1:
        raise ValueError("invalid_interpolation_fraction")
    if first.shape != second.shape or first.ndim != 3 or first.shape[2] != 3:
        raise ValueError("matching_rgb_frames_required")
    h, w = first.shape[:2]
    if forward.shape != (h, w, 2) or backward.shape != (h, w, 2):
        raise ValueError("flow_geometry_mismatch")
    if not np.isfinite(forward).all() or not np.isfinite(backward).all():
        raise ValueError("nonfinite_flow")
    if alpha in (0, 1):
        return (first if alpha == 0 else second).copy(), 1.0
    colors = np.zeros((h * w, 3), dtype=np.float32)
    mass = np.zeros(h * w, dtype=np.float32)
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    masks = confidence or (np.ones((h, w), dtype=np.float32),) * 2
    for image, flow, travel, blend, reliability in (
        (first, forward, alpha, 1 - alpha, masks[0]),
        (second, backward, 1 - alpha, alpha, masks[1]),
    ):
        if reliability.shape != (h, w) or not np.isfinite(reliability).all():
            raise ValueError("invalid_flow_confidence")
        x = xx + flow[..., 0] * travel
        y = yy + flow[..., 1] * travel
        x0 = np.floor(x).astype(np.int32)
        y0 = np.floor(y).astype(np.int32)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            ix, iy = x0 + dx, y0 + dy
            weight = (
                (1 - np.abs(x - ix))
                * (1 - np.abs(y - iy))
                * blend
                * np.clip(reliability, 0, 1)
            )
            valid = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h) & (weight > 0)
            indices = (iy[valid] * w + ix[valid]).ravel()
            contribution = weight[valid].astype(np.float32)
            np.add.at(mass, indices, contribution)
            np.add.at(
                colors, indices, image[valid].astype(np.float32) * contribution[:, None]
            )
    covered = mass > 1e-4
    coverage = float(covered.mean())
    # Tiny unsupported borders retain an endpoint; large holes reject the pair.
    result = (first if alpha <= 0.5 else second).reshape(-1, 3).copy()
    result[covered] = (
        np.rint(colors[covered] / mass[covered, None]).clip(0, 255).astype(np.uint8)
    )
    return result.reshape(h, w, 3), coverage
