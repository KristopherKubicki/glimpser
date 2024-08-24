# utils/video_archiver.py

import datetime
import glob
import os
import re
import subprocess
import tempfile
import time

from werkzeug.utils import secure_filename

from app.config import (
    MAX_COMPRESSED_VIDEO_AGE,
    MAX_IN_PROCESS_VIDEO_SIZE,
    NAME,
    SCREENSHOT_DIRECTORY,
    VERSION,
    VIDEO_DIRECTORY,
)

from .template_manager import get_templates


# TODO: move this to utils so it is not duplicated in routes.py
def validate_template_name(template_name: str):
    if template_name is None or not isinstance(template_name, str):
        return None

    # Strict whitelist of allowed characters
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.')

    # Check if all characters are in the allowed set
    if not all(char in allowed_chars for char in template_name):
        return None

    # Check length
    if len(template_name) == 0 or len(template_name) > 32:
        return None

    # Ensure the name doesn't start or end with a dash or underscore
    if template_name[0] in '-_.' or template_name[-1] in '-_.':
        return None
    if '..' in template_name:
        return None
    if '--' in template_name:
        return None
    if '__' in template_name:
        return None

    # Use secure_filename as an additional safety measure
    sanitized_name = secure_filename(template_name)

    # Ensure secure_filename didn't change the name (which would indicate it found something suspicious)
    if sanitized_name != template_name:
        return None

    return sanitized_name



def touch(fname, times=None):
    with open(fname, "a"):
        os.utime(fname, times)


def trim_group_name(group_name):
    return group_name.replace(" ", "_").lower()


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

    create_command = [
        "ffmpeg", # TODO make this a config value
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

    try:
        subprocess.run(
            create_command, check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        # print(' cmd:', ' '.join(create_command))
        # subprocess.run(create_command)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 300:
            os.rename(output_file, output_file.replace(".tmp", ""))
            return True
        # otherwise, do something? clean up the file maybe?
    except Exception:
        # print("FFmpeg command failed:", ' '.join(create_command), e)
        # log to an error instead!
        if os.path.exists(output_file):
            os.unlink(output_file)


def get_video_duration(video_path):

    if not os.path.exists(video_path):  # raise?
        return None

    """Get the duration of a video in seconds."""
    command = [
        "ffprobe", # TODO: make this a config 
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


def concatenate_videos(in_process_video, temp_video, video_path) -> bool:
    """Concatenate the temporary video with the existing in-process video."""
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
            concat_command = [
                "ffmpeg",
                "-threads",
                "5", # todo, make this a config
                #"-safe",  Option not found?  But it is found and used elsewhere?  Not surewhy this is..
                #"0",
                "-err_detect",
                "ignore_err",
                "-fflags",
                "+igndts+ignidx+genpts+fastseek+discardcorrupt",
                "-an",
                "-dn",
                "-c:v",
                "h264",
                "-i",
                os.path.abspath(in_process_video),
                "-i",
                os.path.abspath(temp_video),
                "-filter_complex",
                "[0:v:0][1:v:0]concat=n=2:v=1:a=0[outv]",
                "-map",
                "[outv]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-y",
                os.path.abspath(concat_video),  # Overwrite the in-process video
            ]
            try:
                # TODO: check stdout and stderr
                subprocess.run(
                    concat_command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                os.rename(concat_video, in_process_video)
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
                handle_concat_error(e, temp_video, in_process_video)
        elif os.path.exists(temp_video) and os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)
    elif os.path.exists(temp_video) and os.path.getsize(temp_video) > 0:
        os.rename(temp_video, in_process_video)

    # TODO: check timestamp, should be current...
    if os.path.exists(in_process_video):
        return True
    return False


def handle_concat_error(e, temp_video, in_process_video) -> bool:
    """Handle errors that occur during the concatenation process."""

    if "/in_process.mp4: Invalid data found" in str(e):
        print("Warning: invalid in_process file", e)
        if os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)
            # TODO: consider truth
    else:
        print("FFmpeg concat command failed:", e) # TODO: handle this better... why non zero exit?
        if os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)


def compile_to_video(camera_path, video_path) -> bool:
    os.makedirs(video_path, exist_ok=True)
    os.makedirs(camera_path, exist_ok=True)

    if not os.path.isdir(video_path) or not os.path.isdir(camera_path):
        return False

    in_process_video = os.path.join(video_path, "in_process.mp4")
    
    # Check if there is an "in-process" video and handle it
    if os.path.isfile(in_process_video):
        file_size_exceeded = os.path.getsize(in_process_video) > MAX_IN_PROCESS_VIDEO_SIZE
        file_age_exceeded = (datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(os.path.getctime(in_process_video))).total_seconds() > MAX_COMPRESSED_VIDEO_AGE * 60 * 60 * 24 * 7

        if file_size_exceeded or file_age_exceeded:
            final_video_name = f"final_{int(os.path.getmtime(in_process_video))}.mp4"
            final_video_path = os.path.join(video_path, final_video_name)
            os.rename(in_process_video, final_video_path)
            logging.info(f"Video finalized: {final_video_path}")

    # Get new image files
    new_files = sorted([
        f for f in glob.glob(os.path.join(camera_path, "*.png"))
        if not os.path.exists(in_process_video) or os.path.getctime(f) > os.path.getmtime(in_process_video)
    ])

    if not new_files:
        return True  # No new files to process

    # Create a temporary file with the list of new frames
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
        for file in new_files:
            if os.path.getsize(file) > 10:
                temp_file.write(f"file '{os.path.abspath(file)}'\n")
        temp_file_path = temp_file.name

    # Create a temporary video with the new frames
    temp_video = os.path.join(video_path, "temp_video.mp4")
    
    create_command = [
        "ffmpeg",
        "-y",  # Overwrite output file if it exists
        "-f", "concat",
        "-safe", "0",
        "-i", temp_file_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",  # Use ultrafast preset for quicker encoding
        "-crf", "23",  # Adjust CRF value for balance between quality and file size
        "-vf", "fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-movflags", "+faststart",
        temp_video
    ]

    try:
        subprocess.run(create_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg command failed: {e}")
        return False
    finally:
        os.remove(temp_file_path)  # Clean up the temporary file

    # Concatenate the temporary video with the existing in-process video
    if os.path.exists(in_process_video):
        concat_command = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", f"concat:{in_process_video}|{temp_video}",
            "-c", "copy",
            os.path.join(video_path, "new_in_process.mp4")
        ]
        try:
            subprocess.run(concat_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.replace(os.path.join(video_path, "new_in_process.mp4"), in_process_video)
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg concatenation failed: {e}")
            return False
    else:
        os.rename(temp_video, in_process_video)

    # Update symlink for latest video
    latest_video_link = os.path.join(VIDEO_DIRECTORY, "latest_camera.mp4")
    if os.path.exists(latest_video_link):
        os.remove(latest_video_link)
    os.symlink(os.path.abspath(in_process_video), latest_video_link)

    return True


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
        except Exception:
            # TODO: log something bad happening
            pass
