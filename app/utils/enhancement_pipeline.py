"""Portable, opt-in enhancement pools and exact-capture display selection.

Pool configuration is administrator-owned and never exposed to browsers. Workers
receive a single bounded image request, never camera URLs or credentials.
"""

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

RECIPES = {
    "neural-colorize": "Neural colorization · inferred color, daylight opt-in",
    "night-adaptive": "Night shadows · multiframe when aligned (not neural)",
    "neural-native": "Neural restoration · native size",
    "neural-lowlight": "Neural restoration + shadow recovery",
    "neural-2x": "Neural restoration + 2× enlargement",
    "gentle": "Gentle denoising · no neural model",
}
ROOT = Path.home() / ".local/share/glimpser-enhancement"
ID = re.compile(r"[a-z][a-z0-9_-]{0,47}")


def pools(path=None):
    """Load a bounded trusted registry; no endpoints or commands from forms."""
    path = Path(
        path
        or os.environ.get(
            "GLIMPSER_ENHANCEMENT_POOLS",
            Path.home() / ".config/glimpser/enhancement-pools.json",
        )
    )
    if not path.exists():
        return {}
    if path.stat().st_size > 65536:
        raise ValueError("pool_registry_too_large")
    config = json.loads(path.read_text())
    if (
        not isinstance(config, dict)
        or config.get("version") != 1
        or not isinstance(config.get("pools"), dict)
    ):
        raise ValueError("invalid_pool_registry")
    result = {}
    for name, value in config["pools"].items():
        if not ID.fullmatch(name) or not isinstance(value, dict):
            raise ValueError("invalid_pool")
        command = value.get("command")
        profiles = value.get("profiles")
        if (
            not isinstance(command, list)
            or not 1 <= len(command) <= 32
            or any(
                not isinstance(arg, str) or not arg or len(arg) > 1024
                for arg in command
            )
            or not isinstance(profiles, list)
            or not profiles
            or any(
                profile not in RECIPES
                and profile
                not in {
                    "neural-deflare",
                    "neural-retinex",
                    "neural-cidnet",
                    "neural-jpeg",
                    "neural-temporal-denoise",
                    "gentle-2x",
                    "neural-smooth",
                    "neural-smooth4",
                    "neural-video-2x",
                }
                for profile in profiles
            )
            or not isinstance(value.get("scope"), str)
            or not ID.fullmatch(value["scope"])
        ):
            raise ValueError("invalid_pool_capabilities")
        result[name] = value
    return result


def pool_choices():
    """Expose names/labels only, never worker addresses or execution arguments."""
    try:
        return [
            {"id": name, "label": str(pool.get("label", name))[:80]}
            for name, pool in pools().items()
            if pool.get("enabled") is True and pool.get("private_media") is True
        ]
    except (OSError, ValueError, TypeError):
        return []


def resolve_pool(name, profile):
    """Require an explicit enabled, confidential-media-capable destination."""
    pool = pools().get(name)
    if (
        not pool
        or pool.get("enabled") is not True
        or pool.get("private_media") is not True
    ):
        raise ValueError("enhancement_pool_unavailable")
    if profile not in pool["profiles"]:
        raise ValueError("enhancement_recipe_not_supported_by_pool")
    return pool


def validate_settings(data):
    """Normalize camera controls and fail closed on unknown pool capabilities."""
    from app.utils.validators import to_bool

    enabled = to_bool(data.get("enhancement_enabled", False))
    display = to_bool(data.get("enhancement_display", False))
    pool = str(data.get("enhancement_pool") or "").strip()
    recipe = str(data.get("enhancement_recipe") or "neural-native")
    if recipe not in RECIPES or (pool and not ID.fullmatch(pool)):
        raise ValueError("invalid_enhancement_settings")
    if enabled:
        resolve_pool(pool, recipe)
    if display and not enabled:
        raise ValueError("enable_enhancement_before_display")
    return dict(
        enhancement_enabled=enabled,
        enhancement_display=display,
        enhancement_pool=pool,
        enhancement_recipe=recipe,
    )


def index_path(camera, root=ROOT):
    """Camera names never become caller-controlled filesystem paths."""
    return root / "live-index" / (hashlib.sha256(camera.encode()).hexdigest() + ".json")


@lru_cache(maxsize=64)
def _hash_version(path, size, mtime, ctime):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_hash(path, maximum=32 * 1024**2):
    stat = path.stat()
    if not 0 < stat.st_size <= maximum:
        raise ValueError("image_out_of_budget")
    return _hash_version(
        str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    )


def display_candidate(camera, source, settings, root=ROOT):
    """Return a labeled derivative only for the exact current source/settings.

    This path does no inference or remote I/O. Any unavailable, changed, rejected
    or corrupt result falls through immediately to the original screenshot.
    """
    if not settings.get("enhancement_enabled") or not settings.get(
        "enhancement_display"
    ):
        return None
    if settings.get("enhancement_recipe") not in RECIPES:
        return None
    try:
        pool = resolve_pool(
            settings.get("enhancement_pool"), settings.get("enhancement_recipe")
        )
        path = index_path(camera, root)
        if path.is_symlink() or path.stat().st_size > 8192:
            return None
        row = json.loads(path.read_text())
        if (
            row.get("camera") != camera
            or row.get("profile") != settings.get("enhancement_recipe")
            or row.get("pool") != settings.get("enhancement_pool")
            or row.get("scope") != pool["scope"]
            or row.get("source_hash") != file_hash(Path(source))
        ):
            return None
        identifier = row.get("id", "")
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            return None
        folder = root / identifier
        metadata = folder / "job.json"
        if (
            folder.is_symlink()
            or metadata.is_symlink()
            or metadata.stat().st_size > 512 * 1024
        ):
            return None
        job = json.loads(metadata.read_text())
        if (
            job.get("state") != "ready"
            or (job.get("processing") or {}).get("review_only") is True
            or job.get("sha256") != row["source_hash"]
            or job.get("pool") != row["pool"]
            or job.get("profile") != row["profile"]
            or job.get("camera") != camera
            or job.get("kind") != "still"
            or (job.get("quality_review") or {}).get("decision") == "reject"
        ):
            return None
        if row.get("profile") == "neural-colorize":
            from scripts.media_enhancement.colorize_policy import eligible

            if job.get("processing", {}).get(
                "color_inferred"
            ) is not True or not eligible(camera, row.get("captured_at")):
                return None
        image = folder / "display.png"
        if image.is_symlink() or file_hash(image, 64 * 1024**2) != row.get(
            "display_hash"
        ):
            return None
        return image, row["profile"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
