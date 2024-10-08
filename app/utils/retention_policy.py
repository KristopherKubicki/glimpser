# utils/retention_policy.py

import os
import time
import logging

from app.config import (
    MAX_COMPRESSED_VIDEO_AGE,
    MAX_RAW_DATA_SIZE,
    SCREENSHOT_DIRECTORY,
    VIDEO_DIRECTORY,
)


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
        print("Warning: file sort error", e)
        return []
    return files


def delete_old_files(file_list, max_age, max_size, minimum=10):
    current_time = time.time()
    total_size = 0

    # sort the list so we keep it in the right date order (it should already be sorted)
    file_list = sorted(file_list, reverse=True)[minimum:]

    # Delete files if total size exceeds the maximum size or they are older than max_age
    # start from oldest to newest
    for file_path in file_list:
        if (
            "in_process." in file_path
            or "last_motion." in file_path
            or "prev_motion." in file_path
        ):
            continue

        try:
            file_age = current_time - os.path.getctime(file_path)
            file_size = os.path.getsize(file_path)
            total_size += file_size

            # Delete files older than max_age or if total size exceeds max_size
            if file_age > max_age * 86400 or total_size > max_size:
                try:
                    os.remove(file_path)
                    total_size -= file_size
                    logging.info("Deleted %s", file_path)
                except Exception as e:
                    logging.warning("Failed to delete %s: %s", file_path, e)
        except FileNotFoundError:
            logging.warning("File not found: %s", file_path)
        except Exception as e:
            logging.error("Error processing %s: %s", file_path, e)


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
