# utils/video_compressor.py

import os
import logging
import subprocess
from app.config import MAX_RAW_DATA_SIZE, VIDEO_DIRECTORY
from app.utils.video_archiver import is_ffmpeg_available

def compress_and_cleanup():
    if not is_ffmpeg_available():
        logging.error("ffmpeg is not available. Video compression skipped.")
        return

    for root, dirs, files in os.walk(VIDEO_DIRECTORY):
        for file in files:
            if file.endswith(".mp4") and not file.startswith("compressed_"):
                input_path = os.path.join(root, file)
                output_path = os.path.join(root, f"compressed_{file}")
                
                # Compress the video
                compress_video(input_path, output_path)
                
                # Check if compression was successful
                if os.path.exists(output_path):
                    # Delete the original file if it exceeds MAX_RAW_DATA_SIZE
                    if os.path.getsize(input_path) > MAX_RAW_DATA_SIZE:
                        os.remove(input_path)
                        logging.info(f"Deleted original file: {input_path}")
                else:
                    logging.error(f"Compression failed for: {input_path}")

def compress_video(input_path, output_path):
    command = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info(f"Successfully compressed: {input_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error compressing video: {e}")