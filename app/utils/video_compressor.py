# utils/video_compressor.py




def compress_and_cleanup():
    # Logic to compress videos using ffmpeg
    # After compression, delete the raw data if the size exceeds MAX_RAW_DATA_SIZE
import ffmpeg

def compress_video(input_path, output_path, quality='medium', is_mobile=False):
    try:
        # Base compression settings
        compression_settings = {
            'vcodec': 'libx264',
            'acodec': 'aac',
            'preset': 'slow',
        }

        # Adjust settings based on quality and device type
        if quality == 'low' or is_mobile:
            compression_settings.update({
                'crf': '28',
                'vf': 'scale=-2:360',  # 360p
                'b:a': '64k',
            })
        elif quality == 'medium':
            compression_settings.update({
                'crf': '23',
                'vf': 'scale=-2:720',  # 720p
                'b:a': '128k',
            })
        else:  # high quality
            compression_settings.update({
                'crf': '18',
                'vf': 'scale=-2:1080',  # 1080p
                'b:a': '192k',
            })

        # Compress the video
        (
            ffmpeg
            .input(input_path)
            .output(output_path, **compression_settings)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )

        print(f"Video compressed successfully: {output_path}")
        return True
    except ffmpeg.Error as e:
        print(f"Error compressing video: {e.stderr.decode()}")
        return False

def compress_and_cleanup(input_path, output_directory, max_raw_data_size):
    # Compress video for different quality levels and device types
    qualities = ['low', 'medium', 'high']
    device_types = [True, False]  # True for mobile, False for desktop

    for quality in qualities:
        for is_mobile in device_types:
            output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}_{quality}_{'mobile' if is_mobile else 'desktop'}.mp4"
            output_path = os.path.join(output_directory, output_filename)
            compress_video(input_path, output_path, quality, is_mobile)

    # Delete raw data if it exceeds MAX_RAW_DATA_SIZE
    if os.path.getsize(input_path) > max_raw_data_size:
        os.remove(input_path)
        print(f"Raw video deleted: {input_path}")
