# utils/video_compressor.py

"""Utility to compress raw screenshot data into videos."""

import logging
import os
import subprocess
from typing import Iterable

from app.config import (
    FFMPEG_HWACCEL,
    FFMPEG_PATH,
    MAX_RAW_DATA_SIZE,
    SCREENSHOT_DIRECTORY,
    VIDEO_DIRECTORY,
)

from .validators import validate_template_name


def _directory_size(paths: Iterable[str]) -> int:
    """Return the combined size of the given files."""

    total = 0
    for path in paths:
        try:
            total += os.path.getsize(path)
        except OSError:
            pass
    return total


def compress_and_cleanup() -> None:
    """Compress screenshots to videos then clean up raw data if needed."""

    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)

    for camera in os.listdir(SCREENSHOT_DIRECTORY):
        if not validate_template_name(camera):
            continue
        camera_dir = os.path.join(SCREENSHOT_DIRECTORY, camera)
        if not os.path.isdir(camera_dir):
            continue

        output_dir = os.path.join(VIDEO_DIRECTORY, camera)
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{camera}.mp4")

        command = [FFMPEG_PATH]
        if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
            command.extend(["-hwaccel", FFMPEG_HWACCEL])
        command.extend(
            [
                "-y",
                "-pattern_type",
                "glob",
                "-i",
                os.path.join(camera_dir, "*.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                output_file,
            ]
        )

        try:
            subprocess.run(
                command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except Exception as e:  # pragma: no cover - log failures only
            logging.error("ffmpeg failed for %s: %s", camera, e)

    # Calculate total raw data size
    raw_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(SCREENSHOT_DIRECTORY)
        for f in files
    ]
    if _directory_size(raw_files) > MAX_RAW_DATA_SIZE:
        for file_path in raw_files:
            try:
                os.remove(file_path)
            except OSError:
                pass

    return None
