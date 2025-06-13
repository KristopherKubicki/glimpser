# utils/retention_policy.py

import logging
import os
import shutil
import time

from app.config import (
    CLIPS_DIRECTORY,
    MAX_CLIP_AGE_MINUTES,
    MAX_COMPRESSED_VIDEO_AGE,
    MAX_RAW_DATA_SIZE,
    SCREENSHOT_DIRECTORY,
    VIDEO_DIRECTORY,
)
from app.utils.screenshots import check_user_activity


def get_files_sorted_by_creation_time(directory):
    if not os.path.isdir(directory):
        return []

    # Get all files with their full path and sort them by creation time in ascending order
    try:
        files = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if not os.path.islink(os.path.join(directory, f))
        ]
        files.sort(key=lambda x: os.path.getctime(x))
    except Exception as e:
        logging.warning("file sort error %s", e)
        return []
    return files


def delete_old_files(file_list, max_age, max_size, minimum=10):
    current_time = time.time()
    total_size = 0

    # `get_files_sorted_by_creation_time` already returns files oldest->newest.
    # Skip the newest `minimum` files so they are preserved.
    files_to_check = file_list[:-minimum] if minimum else file_list

    # Delete files if total size exceeds the maximum size or they are older than max_age
    # start from oldest to newest
    for file_path in files_to_check:
        if (
            "in_process." in file_path
            or "last_motion." in file_path
            or "prev_motion." in file_path
        ):
            continue

        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
                logging.debug("Deleted directory %s", file_path)
                continue

            file_age = current_time - os.path.getctime(file_path)
            file_size = os.path.getsize(file_path)
            total_size += file_size

            # Delete files older than max_age or if total size exceeds max_size
            if file_age > max_age * 86400 or total_size > max_size:
                try:
                    os.remove(file_path)
                    total_size -= file_size
                    logging.debug("Deleted %s", file_path)
                except Exception as e:
                    logging.warning("Failed to delete %s: %s", file_path, e)
        except FileNotFoundError:
            logging.warning("File not found: %s", file_path)
        except Exception as e:
            logging.error("Error processing %s: %s", file_path, e)


def cleanup_clips(max_age_minutes: int = MAX_CLIP_AGE_MINUTES) -> None:
    """Delete stale ``clip.mp4`` files when the user is idle."""

    if not (max_age_minutes and max_age_minutes > 0):
        return

    if check_user_activity(timeout=1):
        # User is active; postpone cleanup to avoid disrupting playback.
        return

    expiry = max_age_minutes * 60
    if not os.path.isdir(CLIPS_DIRECTORY):
        return

    for clip_file in os.listdir(CLIPS_DIRECTORY):
        if not clip_file.endswith(".mp4"):
            continue
        clip_path = os.path.join(CLIPS_DIRECTORY, clip_file)
        if os.path.isfile(clip_path):
            try:
                age = time.time() - os.path.getmtime(clip_path)
                if age > expiry:
                    os.remove(clip_path)
                    logging.debug("Deleted expired clip %s", clip_path)
            except Exception as e:
                logging.warning("Failed to delete %s: %s", clip_path, e)


def retention_cleanup():
    # For each camera, delete old or excess videos
    for camera_name in os.listdir(VIDEO_DIRECTORY):
        camera_dir = os.path.join(VIDEO_DIRECTORY, camera_name)
        video_files = get_files_sorted_by_creation_time(camera_dir)
        delete_old_files(video_files, MAX_COMPRESSED_VIDEO_AGE, MAX_RAW_DATA_SIZE)

    # For each camera, delete old or excess screenshots
    for camera_name in os.listdir(SCREENSHOT_DIRECTORY):
        camera_dir = os.path.join(SCREENSHOT_DIRECTORY, camera_name)
        image_files = get_files_sorted_by_creation_time(camera_dir)
        delete_old_files(image_files, MAX_COMPRESSED_VIDEO_AGE, MAX_RAW_DATA_SIZE)

    cleanup_clips()
