import os
from datetime import datetime


def get_latest_video_date(directory):
    return get_latest_date(directory, ext="mp4")


def get_latest_screenshot_date(directory):
    return get_latest_date(directory, ext="png")


def get_latest_file(directory, ext="png"):

    if not os.path.exists(directory):
        return None

    # rather than search through the files, lets just check the symlink
    lpath = os.path.join(directory + "latest_camera." + ext)
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
            files, key=lambda x: os.path.getctime(os.path.join(directory, x))
        )
    except Exception as e:
        print("Warning: file error", e)
        return None
    return latest_file


def get_latest_date(directory, ext="png"):
    if not os.path.exists(directory):
        return None

    lpath = os.path.join(directory + "latest_camera." + ext)
    latest_file = None
    if os.path.exists(lpath):
        latest_file = lpath
    else:
        latest_file = get_latest_file(directory, ext)

    if latest_file is None:
        return None

    try:
        latest_file_ctime = os.path.getctime(os.path.join(directory, latest_file))
    except Exception as e:
        print("Warning: file error", e)
        return None

    return datetime.fromtimestamp(latest_file_ctime).strftime("%Y-%m-%d %H:%M:%S")
