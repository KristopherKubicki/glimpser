# Video Archiver

The video archiver compiles screenshots into MP4 segments using FFmpeg. Output
files are rotated when they grow too large or when their creation date exceeds
`MAX_COMPRESSED_VIDEO_AGE` days. FFmpeg stdout and stderr are logged to aid
troubleshooting.

Blank screenshots (identified by the `_blank.png` suffix or when the image is
mostly empty) are discarded before any compilation step. This keeps videos free
of placeholder frames.
