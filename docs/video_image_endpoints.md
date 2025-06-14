# Video and Image Endpoints

This guide describes the routes that return or accept video and image data. All routes require authentication unless noted.

## Streaming

### GET `/stream.mp4`

Stream the current MP4 for a camera or group. Pass `camera` or `group` as query parameters. If a camera is specified the `in_process.mp4` file is streamed; otherwise the latest group video is used.

### GET `/live_video`

Stream a camera directly from its configured URL. Provide `camera` as a query parameter. The server automatically restarts the underlying FFmpeg process if it exits unexpectedly.
It now performs a quick HEAD request first and skips launching `ffmpeg` when the camera is unreachable.

### GET `/stream.m3u8`

Return an HLS playlist referencing the latest videos. Optional `camera` or `group` parameters filter the playlist.

### GET `/stream.mjpg`

Continuous MJPEG feed of the newest screenshot. Optional `camera` or `group` parameters limit the stream.

### GET `/fast_stream.mjpg`

Similar to `/stream.mjpg` but captures a fresh frame as quickly as possible. Requires a `camera` parameter. The `/live` page uses this endpoint for near real-time streaming.

### GET `/motion.mjpg`

MJPEG stream containing only motion frames. Accepts `camera` or `group` parameters.

### GET `/caption.mjpg`

MJPEG stream showing the most recent caption frame. Accepts `camera` or `group` parameters.

### GET `/motion_caption.mjpg`

Combines motion and caption frames in one MJPEG stream. Accepts `camera` or `group`.

### GET `/internal_caption.mjpg`

Loops the latest caption text as an MJPEG stream. Accepts `camera` or `group`.

### GET `/test.mjpg`

Basic MJPEG stream useful for verifying connectivity. Optional `camera` or `group` parameters are supported.

### GET `/test_pattern.mjpg`

Streams a generated test pattern with a small spinner and timestamp overlay.

### GET `/stream.png`

Return the most recent screenshot. Optional `camera` or `group` parameters select a specific camera or group. Without parameters the newest frame from any camera is used.

### GET `/rtsp_stream`

Return RTP packets for an active `/test.rtsp` session. Pass the `session` ID as a query parameter.

## Single File Retrieval

### GET `/last_video/<template_name>`

Return the latest MP4 for the template. Falls back to the most recent finalized video if the in‑process file is missing.

### GET `/clip/<template_name>`

Compile a short clip from recent footage. Optional `duration` (seconds) controls the total length. Results are cached under `CLIPS_DIRECTORY`.

### GET `/last_screenshot/<template_name>`

Retrieve the most recent screenshot for the template. If no valid image exists a placeholder PNG is returned with status `404`.

### GET `/last_teaser`

Return the teaser video compiled from recent footage. An optional `group` query parameter fetches a group-specific teaser.

### GET `/videos/<template_name>`

Return a JSON array of MP4 filenames archived for the template.

### GET `/videos/<template_name>/<filename>`

Download a specific video file. Invalid filenames result in `404`.

### GET `/screenshots/<template_name>`

Return a JSON array of screenshot filenames for the template.

### GET `/screenshots/<template_name>/<filename>`

Download a specific screenshot file.

## Upload and Capture

### POST `/submit_image/<template_name>`

Upload an image file as form data under the `file` field. The server timestamps the image and updates the template's last screenshot time.

### POST `/update_video/<template_name>`

Manually compile screenshots for the template into the current video.

### GET or POST `/take_screenshot/<template_name>`

Trigger an immediate screenshot capture. Append `?motion=true` to force motion analysis.

### POST `/record/<template_name>`

Start a short high-speed capture (default 20&nbsp;s). Extra frames are stored for later processing.

### POST `/upload_screenshot/<template_name>`

Upload a screenshot from a local file. The form field name is `image_file`.

### POST `/compile_teaser`

Compile recent footage into a teaser video.
