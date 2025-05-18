import os
from datetime import datetime


def get_latest_video_date(directory):
    return get_latest_date(directory, ext="mp4")


def get_latest_screenshot_date(directory):
    return get_latest_date(directory, ext="png")


def get_latest_file(directory, ext="png"):

    """
    Returns the path to the latest file with the specified extension in a directory.
    
    If a file or symlink named 'latest_camera.<ext>' exists, its path is returned. Otherwise, searches for files with the given extension and returns the one with the most recent modification time. Returns None if the directory does not exist, no matching files are found, or an error occurs during file access.
    
    Args:
        directory: Path to the directory to search.
        ext: File extension to filter by (default is "png").
    
    Returns:
        The path to the latest file as a string, or None if not found.
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
        print("Warning: file error", e)
        return None
    return latest_file

def get_latest_date(directory, ext="png"):
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
        # Get the creation time of the latest file
        latest_file_mtime = os.path.getmtime(latest_file_path)
    except Exception as e:
        print("Warning: file error", e)
        return None

    # Convert the timestamp to UTC datetime string
    #return datetime.utcfromtimestamp(latest_file_mtime).strftime("%Y-%m-%d %H:%M:%S") 
    #  I think there is a risk of double timestamping here, so I removed the UTC conversion
    return datetime.fromtimestamp(latest_file_mtime).strftime("%Y-%m-%d %H:%M:%S")

