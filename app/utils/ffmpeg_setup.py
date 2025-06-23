"""Utilities for building and validating an FFmpeg binary."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path


def get_ffmpeg_path() -> str | None:
    """Return the path to a GPU-enabled FFmpeg build.

    If ``bin/ffmpeg`` does not exist, this function attempts to build it by
    running ``scripts/build_gpu_ffmpeg.sh``. The resulting binary is validated
    with ``-hwaccels``. When the build or validation fails ``None`` is returned.
    """

    repo_root = Path(__file__).resolve().parents[2]
    ffmpeg_bin = repo_root / "bin" / "ffmpeg"
    build_script = repo_root / "scripts" / "build_gpu_ffmpeg.sh"

    if not ffmpeg_bin.exists():
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
