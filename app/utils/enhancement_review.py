"""Private review of preserved originals and labeled enhancement derivatives."""

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / ".local/share/glimpser-enhancement"
IDENTIFIER = re.compile(r"[a-f0-9]{64}")


def archive_root(root):
    """Private local cold storage beside the active library; not a remote backup."""
    return root.with_name(root.name + "-archive")


def job_folder(identifier, root):
    """Resolve retained review links without following archive symlinks."""
    active = root / identifier
    if active.exists() or active.is_symlink():
        return active
    archive = archive_root(root)
    if archive.is_symlink():
        return active
    return archive / identifier


def dimensions(geometry):
    """Describe verified output geometry, omitting absent or malformed values."""
    if not isinstance(geometry, dict):
        return None
    width, height = geometry.get("width"), geometry.get("height")
    if any(type(value) is not int or value <= 0 for value in (width, height)):
        return None
    return f"{width} × {height}"


def method_evidence(row):
    """Expose bounded processing facts, without paths or arbitrary worker text."""
    processing = row.get("processing") or {}
    timeline = processing.get("timeline") or []
    timeline = [item for item in timeline if isinstance(item, dict)]
    counts = Counter(item.get("type") for item in timeline)
    profile = row.get("profile", "")
    methods = {
        "neural-colorize": "DDColor tiny → inferred chroma with original luminance and geometry; no verified color reference; private daylight opt-in",
        "night-adaptive": "Native shadow recovery; aligned multiframe denoising when verified history matches the current capture; not neural",
        "neural-cidnet": "HVI-CIDNet LOLv1-wperc → native overlapping tiles → bounded blend; neutral brightness/saturation controls; review only",
        "neural-retinex": "Retinexformer LOL-v2-real → native overlapping tiles → bounded blend; review only",
        "neural-jpeg": "SwinIR color JPEG artifact reduction (quality-30 model) → native overlapping tiles → bounded blend; review only",
        "neural-temporal-denoise": "FastDVDnet five-frame windows → adjacent-capture and scene-cut gates → bounded blend; no generated frames",
        "neural-deflare": "Flare7K++ Uformer → overlapping native tiles → bounded blend with protected light cores; single frame, review only",
        "neural-lowlight": "Native Real-ESRGAN restoration → multiscale shadow recovery → bounded local contrast; lighting stage is not neural",
        "neural-native": "Native-resolution Real-ESRGAN restoration → 75% neural / 25% original blend",
        "neural-2x": "Real-ESRGAN spatial restoration → 75% neural / 25% Lanczos blend",
        "neural-video-2x": "Per-frame Real-ESRGAN → 75% neural / 25% Lanczos blend; not temporal denoising",
        "neural-smooth": "Bidirectional neural optical flow → confidence gates → 2× frame-rate synthesis or held captures",
        "neural-smooth4": "Bidirectional neural optical flow → confidence gates → 4× frame-rate synthesis or held captures",
        "gentle": "Spatial denoising at native resolution; temporal strength is zero",
        "gentle-2x": "Spatial denoising → conventional 2× Lanczos resize",
    }
    stages = methods.get(profile, "Processing method not recorded")
    if profile == "night-adaptive":
        stages = (
            "Aligned multiframe denoising → native shadow recovery; not neural"
            if processing.get("mode") == "multiframe"
            else "Single-frame native shadow recovery; not neural"
        )
    if (
        profile == "neural-lowlight"
        and (processing.get("lighting") or {}).get("state") == "held"
    ):
        stages = "Native Real-ESRGAN restoration; lighting stage held because the image was already lit"
    preprocessing = row.get("preprocessing") or {}
    if preprocessing.get("method") == "luma-median-chroma-consistent-mean-v1":
        stages = "Aligned multi-frame luminance/chroma denoising → " + stages
    times = row.get("frame_times") or preprocessing.get("capture_times")
    night_reason = None
    capture_span = None
    if profile == "night-adaptive":
        provenance = processing.get("night_provenance") or {}
        if processing.get("mode") == "multiframe" and isinstance(provenance, dict):
            times = provenance.get("capture_times")
            if not (
                isinstance(times, list)
                and 3 <= len(times) <= 5
                and all(type(t) in (int, float) and math.isfinite(t) for t in times)
                and all(0 < b - a <= 120 for a, b in zip(times, times[1:]))
            ):
                times = None
            else:
                capture_span = round(times[-1] - times[0], 1)
        else:
            times = None
            reasons = {
                "no_matching_history": "No matching sequence of recent captures was available.",
                "alignment_uncertain": "The frames could not be aligned confidently.",
                "too_much_changed_area": "Too much of the scene changed between captures.",
                "exposure_mismatch": "The captures had different exposure levels.",
                "not_low_light": "The sequence did not qualify for low-light multiframe processing.",
                "native_resolution_exceeds_neural_budget": "The image exceeded this result's multiframe processing limit.",
                "input_budget": "The capture sequence exceeded the processing budget.",
                "invalid_capture_provenance": "The capture provenance could not be verified.",
                "capture_gap_or_order": "The captures were too far apart or out of order.",
            }
            night_reason = reasons.get(
                processing.get("fallback_reason"),
                "A suitable multiframe sequence was not verified.",
            )
    source_count = (
        len(times)
        if isinstance(times, list)
        else (1 if row.get("kind") == "still" else None)
    )
    if (
        profile == "night-adaptive"
        and processing.get("mode") == "multiframe"
        and times is None
    ):
        source_count = None
    glare = processing.get("glare") or {}
    glare_change = glare.get("mean_absolute_change")
    glare_change = (
        round(glare_change * 100, 2)
        if type(glare_change) in (int, float) and 0 <= glare_change <= 1
        else None
    )
    return {
        "night_fallback_reason": night_reason,
        "capture_span_seconds": capture_span,
        "glare_change_percent": glare_change if profile == "neural-deflare" else None,
        "review_only": processing.get("review_only") is True,
        "stages": stages,
        "input_label": "Multi-frame denoised input to neural stage"
        if preprocessing.get("method") == "luma-median-chroma-consistent-mean-v1"
        else "Original capture",
        "source_frames": source_count,
        "interpolated": counts["interpolated"],
        "held": counts["held"],
        "has_timeline": bool(timeline),
    }


def entry(identifier, root=ROOT):
    """Read bounded job metadata without trusting filesystem paths from JSON."""
    if not IDENTIFIER.fullmatch(identifier):
        return None
    folder = job_folder(identifier, root)
    metadata = folder / "job.json"
    if folder.is_symlink() or metadata.is_symlink():
        return None
    try:
        if metadata.stat().st_size > 512 * 1024:
            return None
        row = json.loads(metadata.read_text())
        if row.get("id") != identifier or row.get("state") != "ready":
            return None
        kind = row.get("kind")
        derivative = "enhanced.png" if kind == "still" else "enhanced.mp4"
        if kind not in {"still", "timelapse"} or row.get("derivative") != derivative:
            return None
        profile = row.get("profile", "")
        processing = row.get("processing", {})
        generated = sum(
            f.get("type") == "interpolated" for f in processing.get("timeline", [])
        )
        label = (
            ("AI interpolated" if generated else "Captured frames held")
            if profile.startswith("neural-smooth")
            else (
                "AI temporal denoising · review only"
                if profile == "neural-temporal-denoise"
                else "AI low-light restoration · review only"
                if profile in {"neural-retinex", "neural-cidnet"}
                else "AI compression cleanup · review only"
                if profile == "neural-jpeg"
                else "AI glare reduction · review only"
                if profile == "neural-deflare"
                else "AI restored · shadow recovery"
                if profile == "neural-lowlight"
                else "AI restored · native resolution"
                if profile == "neural-native"
                else "AI upscaled 2×"
                if profile in {"neural-2x", "neural-video-2x"}
                else "Denoised · native resolution (not neural)"
                if profile == "gentle"
                else "Resized / filtered (not neural)"
            )
        )
        geometry = processing.get("after") or {}
        width, height = geometry.get("width"), geometry.get("height")
        badge = {
            "night-adaptive": "Night shadows",
            "neural-deflare": "AI · glare reduction · review",
            "neural-retinex": "AI · low-light · review",
            "neural-cidnet": "AI · CIDNet low-light · review",
            "neural-jpeg": "AI · compression cleanup · review",
            "neural-temporal-denoise": "AI · temporal denoise · review",
            "neural-2x": "AI · 2× upscale",
            "neural-video-2x": "AI · 2× upscale",
            "neural-native": "AI · restored",
            "neural-lowlight": "AI · restored + lighting",
            "gentle": "Denoised",
            "gentle-2x": "Denoised · 2× resize",
        }.get(profile)
        if profile == "night-adaptive":
            label = "Night shadow recovery · native resolution (not neural)"
            if processing.get("mode") == "multiframe":
                badge = "Multiframe · night shadows"
        if (
            profile == "neural-lowlight"
            and (processing.get("lighting") or {}).get("state") == "held"
        ):
            badge = "AI · restored · lighting held"
            label = "AI restored · lighting unchanged"
        if profile.startswith("neural-smooth"):
            badge = "AI · interpolated" if generated else "Captured frames held"
        if (
            badge
            and (row.get("preprocessing") or {}).get("method")
            == "luma-median-chroma-consistent-mean-v1"
        ):
            badge += " · multi-frame"
        return {
            "review_status": "Rejected for display"
            if (row.get("quality_review") or {}).get("decision") == "reject"
            else "Review pending",
            "badge": badge,
            "pixel_width": width if type(width) is int and width > 0 else None,
            "pixel_height": height if type(height) is int and height > 0 else None,
            "id": identifier,
            "profile": profile,
            "original_width": (
                processing.get("before") or row.get("geometry") or {}
            ).get("width"),
            "original_height": (
                processing.get("before") or row.get("geometry") or {}
            ).get("height"),
            "camera": str(row.get("camera", "Unknown")),
            "kind": kind,
            "label": label,
            "generated": generated,
            "evidence": method_evidence(row),
            "captured_at": float(row["captured_at"]),
            "original_dimensions": dimensions(
                processing.get("before", row.get("geometry"))
            ),
            "enhanced_dimensions": dimensions(processing.get("after")),
            "captured_label": datetime.fromtimestamp(
                float(row["captured_at"]), timezone.utc
            ).strftime("%b %d, %Y · %H:%M UTC"),
            "captured": datetime.fromtimestamp(
                float(row["captured_at"]), timezone.utc
            ).isoformat(),
            "derivative": derivative,
            "source_hash": row["sha256"],
            "enhanced_hash": processing["sha256"],
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def entries(root=ROOT):
    """Return at most 100 ready jobs; none are implicitly approved for rotation."""
    # Filter before limiting: pending jobs must not hide completed comparisons.
    # Capture time, not hash order or processing time, establishes image freshness.
    ready = (
        row for p in root.glob("*/job.json") if (row := entry(p.parent.name, root))
    )
    rows = sorted(ready, key=lambda row: (row["captured_at"], row["id"]), reverse=True)[
        :100
    ]
    for row, note in highlights(rows):
        row["highlight"] = note
    return rows


def highlights(rows):
    """Pick diverse comparison examples, never imply a measured quality ranking."""
    notes = {
        "night-adaptive": "Compare dark areas and moving clouds. The badge distinguishes multiframe denoising from a single-frame shadow lift; neither invents color.",
        "neural-lowlight": "Look at shadow detail, then bright lamps. More brightness is useful only if texture survives and glare stays controlled.",
        "neural-native": "Look at fine edges and grain. Check whether noise is reduced without smearing small objects.",
        "neural-2x": "Use 2× detail to inspect fine edges. Both versions occupy the same area; larger output dimensions alone are not an improvement.",
        "neural-deflare": "Look at the bright reflections and lens rim. The reviewed Backyard trial left them largely unchanged.",
        "neural-retinex": "Look for washed-out highlights and altered texture. The reviewed Backyard trial amplified artifacts.",
        "neural-jpeg": "Look at fine lines and lettering. Smoothing compression can also erase detail.",
        "neural-cidnet": "Look at contrast and bright reflections. The Backyard trials over-brightened the scene.",
        "gentle": "Look at grain in flat areas. This is conventional denoising; the difference may be small.",
    }
    eligible = []
    for row in rows:
        dims = [
            row.get(k)
            for k in (
                "original_width",
                "original_height",
                "pixel_width",
                "pixel_height",
            )
        ]
        if row.get("kind") != "still" or row.get("profile") not in notes:
            continue
        if any(type(v) is not int or v <= 0 for v in dims):
            continue
        w, h, ew, eh = dims
        # Overlays only make sense when both images share the same geometry.
        if abs((w / h) / (ew / eh) - 1) > 0.002:
            continue
        eligible.append(row)
    selected, cameras, profiles = [], set(), set()
    # Favor variety, then fill unused slots with another method from a camera.
    for diverse_cameras in (True, False):
        for row in eligible:
            if row["profile"] in profiles or (
                diverse_cameras and row["camera"] in cameras
            ):
                continue
            selected.append((row, notes[row["profile"]]))
            cameras.add(row["camera"])
            profiles.add(row["profile"])
            if len(selected) == 3:
                return selected
    return selected


def asset(identifier, which, root=ROOT):
    """Serve only a hash-matching original or derivative, never worker metadata."""
    row = entry(identifier, root)
    if not row or which not in {"original", "enhanced"}:
        return None
    path = job_folder(identifier, root) / (
        "source" if which == "original" else row["derivative"]
    )
    expected = row["source_hash" if which == "original" else "enhanced_hash"]
    try:
        if path.is_symlink() or path.stat().st_size > 64 * 1024**2:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            return None
    except OSError:
        return None
    return path, "image/png" if row["kind"] == "still" else "video/mp4"
