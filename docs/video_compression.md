# Video Compression and Cleanup

Glimpser periodically reduces the size of finalized videos to conserve disk space. The `compress_and_cleanup` job re-encodes `final_*.mp4` clips in `VIDEO_DIRECTORY` using `ffmpeg` and removes the original raw files when disk usage grows beyond `MAX_RAW_DATA_SIZE`.

## Compression Flow

1. Scan each camera folder for `final_*.mp4` files that do not already have a `_compressed` counterpart.
2. Invoke `ffmpeg` (respecting `FFMPEG_PATH` and `FFMPEG_HWACCEL`) to create a smaller MP4 with H.264 encoding.
3. After compression, if the combined size of uncompressed clips exceeds `MAX_RAW_DATA_SIZE`, the raw versions are deleted.

Adjust these settings in `app/config.py` to control how much space is retained.
