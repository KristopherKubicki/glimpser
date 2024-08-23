import logging
import os
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse


def capture_frame_with_ytdlp(url, output_path, name="unknown", invert=False):
    """Use yt-dlp to get the video URL and ffmpeg to capture a single frame from the video stream."""
    if shutil.which("yt-dlp") is None:
        print("yt-dlp is not installed or not in the system path.")
        return False

    try:
        ytdlp_command = [
            "yt-dlp",
            "--get-url",
            "--format",
            "bestvideo",
            url,
        ]
        result = subprocess.run(
            ytdlp_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        video_url = result.stdout.decode().strip()

        ffmpeg_command = [
            "ffmpeg",
            "-analyzeduration",
            "20M",
            "-probesize",
            "20M",
            "-ec",
            "15",
            "-i",
            video_url,
            "-sn",
            "-an",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "rgb24",
            "-frames:v",
            "1",
            "-fflags",
            "+igndts+ignidx+genpts+fastseek+discardcorrupt",
            "-q:v",
            "0",
            "-f",
            "image2",
            "-y",
            output_path,
        ]
        subprocess.run(
            ffmpeg_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if os.path.exists(output_path):
            from app.utils.image_processing import add_timestamp

            add_timestamp(output_path, name=name, invert=invert)
            return True
        logging.info(f"Unsuccessfully captured frame from video stream {url}")
    except Exception as e:
        logging.error(f"Error capturing frame with yt-dlp and ffmpeg: {e}")
    return False


def capture_frame_from_stream(
    url, output_path, num_frames=3, timeout=30, name="unknown", invert=False
):
    """Use ffmpeg to capture multiple frames from a video stream and save the last one."""
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not installed or not in the system path.")
        return False

    with tempfile.TemporaryDirectory() as tmpdirname:
        temp_output_pattern = os.path.join(tmpdirname, "frame_%03d.png")
        command = [
            "ffmpeg",
            "-hide_banner",
        ]

        probe_size = "5M"
        if "http:" in url or "https:" in url:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            from app.config import UA

            command.extend(["-headers", f"User-Agent: {UA}\r\n"])
            command.extend(["-headers", f"referer: {base_url}\r\n"])
            command.extend(["-headers", f"origin: {base_url}\r\n"])
            command.extend(["-seekable", "0"])
            probe_size = "5M"
        elif "rtsp:" in url:
            command.extend(["-rtsp_transport", "tcp"])
            probe_size = "10M"
            if "/streaming/" in url.lower():
                command.extend(["-c:v", "h264"])
                command.extend(["-r", "1"])
                probe_size = "20M"
        else:
            probe_size = "20M"

        command.extend(["-analyzeduration", probe_size])
        command.extend(["-probesize", probe_size])
        command.extend(
            [
                "-use_wallclock_as_timestamps",
                "1",
                "-threads",
                "1",
                "-skip_frame",
                "nokey",
                "-sn",
                "-an",
                "-i",
                url,
                "-movflags",
                "+faststart",
                "-pix_fmt",
                "rgb24",
                "-frames:v",
                str(num_frames),
                "-fflags",
                "+igndts+ignidx+genpts+fastseek+discardcorrupt",
                "-q:v",
                "0",
                "-f",
                "image2",
                temp_output_pattern,
            ]
        )

        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=17,
            )

            frames = sorted(
                os.listdir(tmpdirname),
                key=lambda x: os.path.getsize(os.path.join(tmpdirname, x)),
            )
            if frames:
                last_frame_path = os.path.join(tmpdirname, frames[-1])
                shutil.move(last_frame_path, output_path)
                if os.path.exists(output_path):
                    from app.utils.image_processing import add_timestamp

                    add_timestamp(output_path, name=name, invert=invert)
                    logging.info(f"Successfully captured frame from stream {url}")
                    return True
            else:
                logging.error(f"No frames captured from stream {url}")
        except Exception as e:
            logging.error(f"Error capturing frames from stream: {e}")

    logging.error(f"Error capturing frame with ffmpeg: {url}")
    return False
