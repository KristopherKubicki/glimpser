"""Helper utilities to summarize video and screenshot directories.

Functions return timestamps of the latest files and resolve symlinks like
``latest_camera.png`` so the UI can quickly display recent activity.
Errors are logged but not raised to keep dashboards responsive even when
files are missing.
"""

import logging
import os
from datetime import datetime


def get_latest_video_date(directory):
    """Return the timestamp of the newest ``.mp4`` in ``directory``.

    Parameters
    ----------
    directory: str
        Folder to search for video files.

    Returns
    -------
    str | None
        Timestamp formatted as ``"%Y-%m-%d %H:%M:%S"`` or ``None`` if no file is
        found.
    """

    return get_latest_date(directory, ext="mp4")


def get_latest_screenshot_date(directory):
    """Return the timestamp of the newest ``.png`` in ``directory``.

    This helper mirrors :func:`get_latest_video_date` but searches for
    screenshot files instead of videos.

    Parameters
    ----------
    directory: str
        Folder to search for screenshot files.

    Returns
    -------
    str | None
        Timestamp formatted as ``"%Y-%m-%d %H:%M:%S"`` or ``None`` if no file is
        found.
    """

    return get_latest_date(directory, ext="png")


def get_latest_file(directory, ext="png"):
    """Return the most recent file name within ``directory``.

    Parameters
    ----------
    directory: str
        Folder to search.
    ext: str, optional
        File extension to filter for. Defaults to ``"png"``.

    Returns
    -------
    str | None
        Path to ``latest_camera.<ext>`` when present, otherwise the name of the
        newest matching file or ``None`` if no file exists.
    """

    if not os.path.exists(directory):
        return None

    # rather than search through the files, lets just check the symlink
    lpath = os.path.join(directory, f"latest_camera.{ext}")
    if os.path.exists(lpath):
        return lpath

    files = [
        f
        for f in os.listdir(directory)
        if f.endswith("." + ext) and os.path.isfile(os.path.join(directory, f))
    ]
    if not files:
        return None
    try:
        latest_file = max(
            files, key=lambda x: os.path.getmtime(os.path.join(directory, x))
        )
    except Exception as e:
        logging.warning("file error %s", e)
        return None
    return latest_file


def get_latest_date(directory, ext="png"):
    """Return a formatted timestamp for the newest file in ``directory``.

    Parameters
    ----------
    directory: str
        Directory to inspect.
    ext: str, optional
        File extension to filter for. Defaults to ``"png"``.

    Returns
    -------
    str | None
        Timestamp of the latest file in ``"%Y-%m-%d %H:%M:%S"`` format or
        ``None`` if nothing is found.
    """

    if not os.path.exists(directory):
        return None

    # Correctly join directory and filename
    lpath = os.path.join(directory, f"latest_camera.{ext}")
    latest_file = None

    if os.path.exists(lpath):
        # If 'latest_camera.<ext>' exists, use its filename
        latest_file = f"latest_camera.{ext}"
    else:
        # Assume 'get_latest_file' returns just the filename
        latest_file = get_latest_file(directory, ext)

    if latest_file is None:
        return None

    try:
        # Construct the full path to the latest file
        latest_file_path = os.path.join(directory, latest_file)
        # Get the modification time of the latest file
        latest_file_mtime = os.path.getmtime(latest_file_path)
    except Exception as e:
        logging.warning("file error %s", e)
        return None

    # Always return timestamps in UTC for consistency across the codebase
    return datetime.utcfromtimestamp(latest_file_mtime).strftime("%Y-%m-%d %H:%M:%S")
