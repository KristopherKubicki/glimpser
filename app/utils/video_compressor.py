# utils/video_compressor.py

"""Utility for compressing finalized videos and removing raw footage."""

import logging
import os
import subprocess

from app.config import (
    FFMPEG_HWACCEL,
    FFMPEG_PATH,
    MAX_RAW_DATA_SIZE,
    VIDEO_DIRECTORY,
)


def _iter_raw_videos():
    """Yield paths of raw video files ready for compression."""

    for camera in os.listdir(VIDEO_DIRECTORY):
        camera_dir = os.path.join(VIDEO_DIRECTORY, camera)
        if not os.path.isdir(camera_dir):
            continue
        for fname in os.listdir(camera_dir):
            if (
                fname.startswith("final_")
                and fname.endswith(".mp4")
                and "_compressed" not in fname
            ):
                yield os.path.join(camera_dir, fname)


def _raw_size():
    """Return total size of raw (uncompressed) video files."""

    size = 0
    for path in _iter_raw_videos():
        try:
            size += os.path.getsize(path)
        except Exception as e:  # pragma: no cover - ignore missing files
            logging.warning("size calc error %s: %s", path, e)
    return size


def compress_and_cleanup():
    """Compress finalized videos and remove raw copies when necessary."""

    for raw_path in list(_iter_raw_videos()):
        compressed_path = raw_path.replace(".mp4", "_compressed.mp4")
        if not os.path.exists(compressed_path):
            cmd = [FFMPEG_PATH]
            if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
                cmd.extend(["-hwaccel", FFMPEG_HWACCEL])
            cmd.extend(
                [
                    "-i",
                    raw_path,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "28",
                    "-movflags",
                    "+faststart",
                    "-y",
                    compressed_path,
                ]
            )
            try:
                subprocess.run(
                    cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
            except Exception as e:  # pragma: no cover - logged
                logging.error("ffmpeg failed on %s: %s", raw_path, e)
                continue

        if _raw_size() > MAX_RAW_DATA_SIZE:
            try:
                os.remove(raw_path)
                logging.debug("removed raw video %s", raw_path)
            except Exception as e:  # pragma: no cover - logged
                logging.warning("failed to remove %s: %s", raw_path, e)
