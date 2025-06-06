# utils/video_archiver.py

import datetime
import glob
import os
import re
import subprocess
import tempfile
import time
import logging
from PIL import Image

from app.utils.screenshots import is_mostly_blank
from enum import Enum, auto

from .validators import validate_template_name

from app.config import (
    MAX_COMPRESSED_VIDEO_AGE,
    MAX_IN_PROCESS_VIDEO_SIZE,
    NAME,
    SCREENSHOT_DIRECTORY,
    VERSION,
    VIDEO_DIRECTORY,
    FFMPEG_PATH,
    FFPROBE_PATH,
    FFMPEG_HWACCEL,
    FFMPEG_THREADS,
)

from .template_manager import get_templates


class ConcatStatus(Enum):
    """Return codes for concatenation handling."""

    RECOVERED = auto()
    RETRY = auto()
    FATAL = auto()


def touch(fname, times=None):
    with open(fname, "a"):
        os.utime(fname, times)


def trim_group_name(group_name):
    """Normalize a group name by replacing spaces with underscores and converting to lowercase."""
    return group_name.replace(" ", "_").lower()


def run_ffmpeg(command, timeout: int = 30):
    """Execute an FFmpeg command and log output.

    Parameters
    ----------
    command: list[str]
        Full ffmpeg command to execute.
    timeout: int, optional
        Number of seconds before the process is terminated. Defaults to 30.
    """
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if result.stdout:
        logging.debug("ffmpeg stdout: %s", result.stdout.strip())
    if result.stderr:
        logging.debug("ffmpeg stderr: %s", result.stderr.strip())
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, command, output=result.stdout, stderr=result.stderr
        )
    return result


def pipe_ffmpeg_frames(command, frame_files):
    """Stream image frames to FFmpeg through stdin."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for frame in frame_files:
        with open(frame, "rb") as img:
            process.stdin.write(img.read())
    process.stdin.close()
    stdout, stderr = process.communicate()
    if stdout:
        logging.debug("ffmpeg stdout: %s", stdout.decode().strip())
    if stderr:
        logging.debug("ffmpeg stderr: %s", stderr.decode().strip())
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, command, output=stdout, stderr=stderr
        )
    return process


def get_video_creation_time(video_path):
    """Return the creation_time metadata as a datetime object."""
    command = [
        FFPROBE_PATH,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "format_tags=creation_time",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        os.path.abspath(video_path),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.stdout.strip():
            ctime = result.stdout.strip().replace("Z", "")
            return datetime.datetime.fromisoformat(ctime)
    except Exception as e:
        logging.debug("ffprobe error %s", e)
    return None


def is_video_expired(video_path, max_age_days):
    """Return True if the video is older than max_age_days."""
    if not os.path.exists(video_path):
        return False
    now = datetime.datetime.utcnow()
    try:
        ctime = datetime.datetime.fromtimestamp(os.path.getctime(video_path))
        age = (now - ctime).total_seconds()
    except Exception:
        age = 0
    meta_time = get_video_creation_time(video_path)
    if meta_time:
        age = max(age, (now - meta_time).total_seconds())
    return age > max_age_days * 86400


def compile_to_teaser():
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    final_videos = {}

    if not os.path.isdir(VIDEO_DIRECTORY):
        return False

    with tempfile.NamedTemporaryFile(mode="w+") as temp_file:
        templates = get_templates()

        for camera, template in templates.items():
            camera_path = os.path.join(VIDEO_DIRECTORY, camera)
            os.makedirs(camera_path, exist_ok=True)

            # Get the most recent "in_process.mp4" video
            video_files = sorted(
                glob.glob(camera_path + "/*in_process.mp4"), reverse=True
            )
            if video_files:
                latest_video = video_files[0]
                ldur = get_video_duration(latest_video)
                if ldur < 1:  # not much going on...
                    continue

                # Extract the last 5 seconds of the video
                temp_file.write(f"file '{os.path.abspath(latest_video)}'\n")
                temp_file.write(f"inpoint {max(ldur - 5, 0)}\n")
                temp_file.write(f"outpoint {ldur}\n")

                # Add to group-specific final videos
                groups = template.get("groups", "").split(",")
                for group in groups:
                    trimmed_group_name = group.strip().replace(" ", "_")
                    if trimmed_group_name:
                        if trimmed_group_name not in final_videos:
                            final_videos[trimmed_group_name] = []
                        final_videos[trimmed_group_name].append(
                            os.path.abspath(latest_video)
                        )

        # Concatenate the videos without re-encoding for all cameras
        compile_videos(
            temp_file.name, os.path.join(VIDEO_DIRECTORY, "all_in_process.mp4")
        )

        # Concatenate the videos for each group
        for group, videos in final_videos.items():
            with tempfile.NamedTemporaryFile(
                mode="w+"
            ) as group_temp_file:  # should be cleaning up automatically...
                for video in videos:
                    group_temp_file.write(f"file '{video}'\n")
                group_temp_file.flush()
                compile_videos(
                    group_temp_file.name,
                    os.path.join(VIDEO_DIRECTORY, f"{group}_in_process.mp4"),
                )


def compile_videos(input_file, output_file):

    if not os.path.exists(input_file):
        return False

    create_command = [FFMPEG_PATH]
    if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
        create_command.extend(["-hwaccel", FFMPEG_HWACCEL])
    create_command.extend(
        [
            "-threads",
            "5",
            "-err_detect",
            "ignore_err",
            "-fflags",
            "+igndts+ignidx+genpts+fastseek+discardcorrupt",
            "-an",
            "-dn",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            os.path.abspath(input_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-y",
            os.path.abspath(output_file),
        ]
    )

    try:
        run_ffmpeg(create_command, timeout=30)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 300:
            if is_video_expired(output_file, MAX_COMPRESSED_VIDEO_AGE):
                logging.info("Rotating expired output %s", output_file)
            os.rename(output_file, output_file.replace(".tmp", ""))
            return True
        # otherwise, do something? clean up the file maybe?
    except Exception as e:
        logging.error("FFmpeg command failed: %s", e)
        if os.path.exists(output_file):
            os.unlink(output_file)


def get_video_duration(video_path):

    if not os.path.exists(video_path):  # raise?
        return None

    """Get the duration of a video in seconds."""
    command = [
        FFPROBE_PATH,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        os.path.abspath(video_path),
    ]
    duration = 0
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        duration = float(result.stdout.strip())
    except Exception:
        pass
    return duration


def concatenate_videos(in_process_video, temp_video, video_path, retries=1) -> bool:
    """Concatenate the temporary video with the existing in-process video."""
    file_updated = False

    if (
        os.path.exists(in_process_video)
        and os.path.exists(temp_video)
        and os.path.getsize(in_process_video) > 0
        and os.path.getsize(temp_video) > 0
        and os.path.isdir(video_path)
    ):
        in_process_duration = get_video_duration(in_process_video)
        temp_video_duration = get_video_duration(temp_video)
        if in_process_duration > 0 and temp_video_duration > 0:
            concat_video = os.path.join(video_path, "in_process.concat.mp4")
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt") as f:
                f.write(f"file '{os.path.abspath(in_process_video)}'\n")
                f.write(f"file '{os.path.abspath(temp_video)}'\n")
                f.flush()

                concat_command = [FFMPEG_PATH]
                if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
                    concat_command.extend(["-hwaccel", FFMPEG_HWACCEL])
                concat_command.extend(
                    [
                        "-threads",
                        str(FFMPEG_THREADS),
                        "-err_detect",
                        "ignore_err",
                        "-fflags",
                        "+igndts+ignidx+genpts+fastseek+discardcorrupt",
                        "-an",
                        "-dn",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        f.name,
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        "-y",
                        os.path.abspath(concat_video),
                    ]
                )
                try:
                    run_ffmpeg(concat_command)
                    os.rename(concat_video, in_process_video)
                    file_updated = True
                    output_video = os.path.join(VIDEO_DIRECTORY, "latest_camera.mp4")
                    if os.path.exists(output_video + ".tmp"):
                        os.unlink(output_video + ".tmp")
                    os.symlink(
                        os.path.abspath(in_process_video),
                        os.path.abspath(output_video + ".tmp"),
                    )
                    os.rename(
                        os.path.abspath(output_video + ".tmp"),
                        os.path.abspath(output_video),
                    )

                except Exception as e:
                    status = handle_concat_error(e, temp_video, in_process_video)
                    if status == ConcatStatus.RETRY and retries > 0:
                        logging.info("Retrying concatenation due to transient error")
                        time.sleep(1)
                        return concatenate_videos(
                            in_process_video,
                            temp_video,
                            video_path,
                            retries=retries - 1,
                        )
                    elif status == ConcatStatus.RECOVERED:
                        return True
                    else:
                        return False
        elif os.path.exists(temp_video) and os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)
            file_updated = True
    elif os.path.exists(temp_video) and os.path.getsize(temp_video) > 0:
        os.rename(temp_video, in_process_video)
        file_updated = True

    # Verify the modification time is recent when a file was updated
    if os.path.exists(in_process_video):
        if file_updated:
            mod_time = os.path.getmtime(in_process_video)
            if abs(time.time() - mod_time) > 10:
                logging.warning(
                    "in_process video timestamp stale: %s", in_process_video
                )
                return False
        return True
    return False


def handle_concat_error(e, temp_video, in_process_video) -> ConcatStatus:
    """Handle errors that occur during the concatenation process.

    Returns a :class:`ConcatStatus` indicating how the caller should proceed.
    """

    message = str(e)

    if "Invalid data found" in message:
        logging.warning("invalid in_process file %s", message)
        if os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)
        return ConcatStatus.RECOVERED

    if "temporarily unavailable" in message or "Resource busy" in message:
        logging.warning("transient ffmpeg error: %s", message)
        return ConcatStatus.RETRY

    logging.error("FFmpeg concat command failed: %s", message)
    if os.path.getsize(temp_video) > 0:
        os.rename(temp_video, in_process_video)
    return ConcatStatus.FATAL


def compile_to_video(camera_path, video_path) -> bool:

    os.makedirs(video_path, exist_ok=True)
    os.makedirs(camera_path, exist_ok=True)

    if not os.path.isdir(video_path):
        return False
    if not os.path.isdir(camera_path):
        return False

    in_process_video = os.path.join(video_path, "in_process.mp4")

    # Check size and age of the in-process video for rotation
    if os.path.isfile(in_process_video):
        file_size_exceeded = (
            os.path.getsize(in_process_video) > MAX_IN_PROCESS_VIDEO_SIZE
        )
        file_age_exceeded = is_video_expired(in_process_video, MAX_COMPRESSED_VIDEO_AGE)

        # consider when the length is 2x300 frames as well so we always
        # have perfect overlap at 2x

        if file_size_exceeded or file_age_exceeded:
            # Rename the "in-process" video to a "final" video with a timestamp
            final_video_name = f"final_{int(os.path.getmtime(in_process_video))}.mp4"
            final_video_path = os.path.join(video_path, final_video_name)
            os.rename(in_process_video, final_video_path)
            # print(f'Video finalized: {final_video_path}')
            # this is going to generate overlapping segments, which is OK for now .

    # Get the modification time of the in-process video
    video_mod_time = 0
    ldur = 0
    if os.path.exists(in_process_video):
        video_mod_time = os.path.getmtime(in_process_video)
        ldur = get_video_duration(in_process_video)
        if (
            ldur < 10 and time.time() - video_mod_time > 60 * 60
        ):  # could be a waste of 300 frames...
            # print("  skipping ", in_process_video, ldur, time.time() - video_mod_time)
            video_mod_time = 0
            # go bigger...

    # Finalize when roughly 600 frames (~24s) have been assembled.  Allow a
    # small tolerance for rounding errors from FFprobe so the file rotates
    # when the recording actually completes.
    rotation_threshold = (300 / 25) * 2  # two 12 second segments
    if os.path.exists(in_process_video) and ldur >= rotation_threshold - 0.1:
        final_video_name = f"final_{int(os.path.getmtime(in_process_video))}.mp4"
        final_video_path = os.path.join(video_path, final_video_name)
        os.rename(in_process_video, final_video_path)
        # we should finalize at the END of the encode , right?
        # print(f'Video finalized: {final_video_path}')  #log instead
        # this is going to generate overlapping segments, which is OK for now .

    # print("OK", glob.glob(camera_path + "/*.png"))

    # Filter the list of image files to include only those that are newer than the video
    # Files may disappear between the glob and metadata lookup so catch
    # FileNotFoundError and skip missing entries.
    new_files = []
    for f in glob.glob(os.path.join(camera_path, "*.png")):
        if os.path.islink(f):
            continue
        if f.endswith("_blank.png"):
            continue
        try:
            if os.path.getctime(f) > video_mod_time:
                new_files.append(f)
        except FileNotFoundError:
            # Screenshot was removed concurrently; ignore it
            continue

    # Drop nearly blank images
    filtered_files = []
    for file in new_files:
        try:
            with Image.open(file) as img:
                if not is_mostly_blank(img):
                    filtered_files.append(file)
        except Exception:
            continue

    new_files = sorted(filtered_files)

    # print("compile", time.time(), video_mod_time, len(new_files))

    if len(new_files) > 0:
        frame_files = [
            f
            for f in new_files[-300:]
            if os.path.getsize(os.path.abspath(f)) > 10 and "_2" in f
        ]
        if not frame_files:
            return

        temp_video = os.path.join(video_path, "in_process.tmp.mp4")

        create_command = [FFMPEG_PATH]
        if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
            create_command.extend(["-hwaccel", FFMPEG_HWACCEL])
        create_command.extend(
            [
                "-threads",
                "5",
                "-f",
                "image2pipe",
                "-r",
                "25",
                "-vcodec",
                "png",
                "-i",
                "pipe:0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-movflags",
                "+faststart",
            ]
        )
        create_command.extend(
            ["-metadata", "creation_time=%sZ" % datetime.datetime.utcnow()]
        )
        create_command.extend(["-metadata", f"encoded_by={NAME}"])
        create_command.extend(["-metadata", f"version={VERSION}"])
        create_command.extend(["-y", os.path.abspath(temp_video)])

        try:
            pipe_ffmpeg_frames(create_command, frame_files)
            if is_video_expired(temp_video, MAX_COMPRESSED_VIDEO_AGE):
                logging.warning("creation time mismatch for %s", temp_video)
        except Exception as e:
            logging.error("FFmpeg command failed: %s", e)
        finally:
            if os.path.exists(temp_video) and os.path.getsize(temp_video) > 0:
                if video_mod_time == 0:
                    os.rename(temp_video, in_process_video)
                else:
                    ldur2 = get_video_duration(temp_video)
                    if os.path.getsize(temp_video) > 0 and ldur2 == 300 / 25:
                        os.rename(temp_video, in_process_video)
                    elif round(ldur2, 1) == round((len(frame_files) / 25), 1):
                        concatenate_videos(in_process_video, temp_video, video_path)
                    else:
                        concatenate_videos(in_process_video, temp_video, video_path)

    # Frames are encoded into temporary segments. When an existing
    # in-process video is present, segments are concatenated using the
    # concat demuxer without re-encoding.


def archive_screenshots():
    """Background job to compile screenshots into videos."""
    # Ensure VIDEO_DIRECTORY exists
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)

    for camera_name in os.listdir(SCREENSHOT_DIRECTORY):
        if not validate_template_name(camera_name):
            continue
        camera_path = os.path.join(SCREENSHOT_DIRECTORY, camera_name)
        if not os.path.isdir(camera_path):  # just a file
            continue
        video_path = os.path.join(VIDEO_DIRECTORY, camera_name)
        os.makedirs(camera_path, exist_ok=True)
        os.makedirs(video_path, exist_ok=True)

        try:
            compile_to_video(camera_path, video_path)
        except Exception as e:
            logging.exception("Failed to compile video for camera %s", camera_name)
