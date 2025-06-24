"""Utilities for building and validating an FFmpeg binary."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path


def get_ffmpeg_path() -> str | None:
    """Return the path to a GPU-enabled FFmpeg build if available.

    The binary is validated with ``-hwaccels`` when present. Automatic
    building is disabled by default. Set ``GLIMPSER_AUTO_BUILD_FFMPEG=1`` to
    build ``bin/ffmpeg`` using ``scripts/build_gpu_ffmpeg.sh``. When building
    or validation fails ``None`` is returned.
    """

    repo_root = Path(__file__).resolve().parents[2]
    ffmpeg_bin = repo_root / "bin" / "ffmpeg"
    build_script = repo_root / "scripts" / "build_gpu_ffmpeg.sh"
    auto_build = os.getenv("GLIMPSER_AUTO_BUILD_FFMPEG") == "1"

    if not ffmpeg_bin.exists():
        if not auto_build:
            logging.info(
                "FFmpeg binary not found; set GLIMPSER_AUTO_BUILD_FFMPEG=1 to build automatically"
            )
            return None
        if not build_script.exists():
            logging.error("Missing build script: %s", build_script)
            return None
        try:
            subprocess.check_call(["bash", str(build_script)], timeout=1800)
        except Exception as exc:  # pragma: no cover - build failures
            logging.error("FFmpeg build failed: %s", exc)
            return None

    try:
        subprocess.check_call(
            [str(ffmpeg_bin), "-hwaccels"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception as exc:
        logging.error("FFmpeg validation failed: %s", exc)
        return None

    return str(ffmpeg_bin)
