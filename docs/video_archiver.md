# Video Archiver

The video archiver compiles screenshots into MP4 segments using FFmpeg. Output
files are rotated when they grow too large or when their creation date exceeds
`MAX_COMPRESSED_VIDEO_AGE` days. FFmpeg stdout and stderr are logged to aid
troubleshooting.

Errors encountered during compilation are logged with the camera name so that
failures can be diagnosed easily.

Blank screenshots (identified by the `_blank.png` suffix or when the image is
mostly empty) are discarded before any compilation step. This keeps videos free
of placeholder frames.

If a screenshot vanishes between discovery and metadata lookup (for example, if
another process cleans the directory), the archiver simply skips that file. This
prevents crashes due to `FileNotFoundError` when gathering timestamps.

When segments are concatenated, the resulting `in_process.mp4` is checked to
ensure its modification time is recent. A stale timestamp triggers a warning
and the operation is aborted so corrupted videos do not linger.

Videos automatically rotate into a `final_*.mp4` once roughly 600 frames
(about 24 seconds) accumulate. A small tolerance in the duration check prevents
rounding errors from delaying rotation.
