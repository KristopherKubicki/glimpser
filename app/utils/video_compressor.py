# utils/video_compressor.py

"""Utility helpers for compressing raw videos and cleaning up space."""

import logging
import os
import subprocess

from app.config import FFMPEG_PATH, MAX_RAW_DATA_SIZE, VIDEO_DIRECTORY
from .retention_policy import retention_cleanup


def _compress_video(src, dest):
    """Compress ``src`` to ``dest`` using ffmpeg."""
    command = [
        FFMPEG_PATH,
        "-y",
        "-i",
        os.path.abspath(src),
        "-vcodec",
        "libx264",
        "-crf",
        "28",
        os.path.abspath(dest),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def compress_and_cleanup():
    """Compress videos under ``VIDEO_DIRECTORY`` and enforce size limits."""

    for root, _, files in os.walk(VIDEO_DIRECTORY):
        for file in files:
            if file.endswith(".mp4") and not file.endswith(".compressed.mp4"):
                src = os.path.join(root, file)
                compressed = os.path.join(root, file.replace(".mp4", ".compressed.mp4"))
                if os.path.exists(compressed):
                    continue
                try:
                    _compress_video(src, compressed)
                    if os.path.exists(compressed) and os.path.getsize(compressed) < os.path.getsize(src):
                        os.remove(src)
                    else:
                        os.remove(compressed)
                except Exception as e:
                    logging.error("Video compression failed for %s: %s", src, e)

    total_size = 0
    for root, _, files in os.walk(VIDEO_DIRECTORY):
        for file in files:
            path = os.path.join(root, file)
            if os.path.exists(path):
                total_size += os.path.getsize(path)

    if total_size > MAX_RAW_DATA_SIZE:
        retention_cleanup()
