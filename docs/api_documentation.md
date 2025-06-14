# Glimpser API Documentation

This document outlines the API endpoints available in Glimpser for programmatic interaction with the application.

## Authentication

Most API requests require a valid session or API key. A few informational endpoints such as `/api/discover` and `/login` are accessible without authentication. When an API key is needed, include it in the request header:

```
Authorization: Bearer YOUR_API_KEY
```

## Security Headers

All responses now include standard security headers to help prevent
common attacks. Important headers are:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: no-referrer`
- `Cache-Control: no-store`

## Endpoints

The current build exposes a limited API focused on template management and
capturing images. Earlier versions of this documentation referenced a more
comprehensive `/api/v1/*` interface, but those endpoints are not implemented.
Below are the available routes.

### 1. Manage Templates

**GET /templates**

Fetch a JSON list of configured templates. Optional query parameters `group` and `search` can be used to filter results.

Example response:

```json
{
  "camera1": { "url": "rtsp://example" }
}
```

**POST /templates**

Create or update a template. Provide template details as JSON.

Example request:

```json
{
  "name": "camera1",
  "url": "rtsp://example"
}
```

Example response:

```json
{ "status": "success", "message": "Template saved" }
```

Saving a template automatically stops any scheduled job for that
camera and reschedules it using the updated parameters.

**DELETE /templates**

Remove a template by name.

Example request:

```json
{ "name": "camera1" }
```

Example response:

```json
{ "status": "success", "message": "Template deleted" }
```

### 2. View and Update Settings

**GET /settings**

Requires authentication via session or API key.
Returns the settings page in HTML format.

**POST /settings**

Requires authentication. Submit form data to modify configuration values. A successful update redirects back to the settings page.

### 3. Stream MP4 Video

**GET /stream.mp4**

Stream the most recent MP4 video. Provide either a `camera` or `group` query
parameter to restrict the feed. When a camera is specified the current
`in_process.mp4` for that camera is streamed; otherwise the latest group video
is returned. The video is served in small chunks and loops continuously.

Examples:
`/stream.mp4?camera=frontdoor` or `/stream.mp4?group=frontdoor`

### 4. Stream Live Video

**GET /live_video**

Stream a camera directly from its configured URL in real time. Specify `camera` as a query parameter.

Example: `/live_video?camera=frontdoor`

If the underlying `ffmpeg` process exits unexpectedly the server now
restarts it automatically. When repeated failures occur the delay between
attempts grows exponentially (up to 30 seconds) to reduce log spam. This
ensures the client receives a valid MP4 stream whenever the camera becomes
available again while avoiding rapid restarts.

### 5. Additional Streaming Endpoints

Several other routes provide streaming functionality:

- **GET /stream.mjpg** – Continuous MJPEG stream of the latest camera image. Optional `camera` or `group` query parameters limit the feed. Passing `group=all` shows the newest frame from any camera.
- **GET /stream.png** – Returns the most recent screenshot. Optional `camera` or `group` parameters filter the result.
- **GET /motion.mjpg** – MJPEG stream containing only motion frames. Accepts `camera` or `group` as query parameters.
- **GET /caption.mjpg** – MJPEG stream of the last caption frame for a group.
- **GET /motion_caption.mjpg** – Combines motion and caption frames in a single MJPEG stream.
- **GET /internal_caption.mjpg** – Loops the latest caption text as an MJPEG stream. Accepts `camera` or `group` to limit captions.
- **GET /stream.m3u8** – HLS playlist referencing the latest videos.
  Optional `camera` or `group` query parameters filter the playlist to a
  single camera or group of cameras.
- **GET /last_video/<template_name>** – Download the most recent MP4 for the given template. Returns a 404 response if no video is available.
- **GET /last_screenshot/<template_name>** – Retrieve the latest screenshot for a template.
- **GET /last_teaser** – Returns the teaser video compiled from recent footage. Accepts an optional `group` query parameter to retrieve a group-specific teaser, e.g. `/last_teaser?group=frontdoor`.
- **GET /clip/<template_name>** – Concatenate the active `in_process.mp4` with recent finalized segments. If the in‑progress video is shorter than the requested `duration` (default `DEFAULT_CLIP_DURATION`) older finalized clips are prepended. When no footage exists the server falls back to a blank video. Subsequent requests reuse the cached clip stored under `CLIPS_DIRECTORY` for speed. Responses include `Cache-Control: public, max-age=120` so browsers retain the clip for two minutes.
- **GET /test.rtsp** – Basic RTSP endpoint that serves MJPEG frames when used with `/rtsp_stream`. Send periodic `GET_PARAMETER` requests to keep the session alive.
- **GET /test.mjpg** – MJPEG view of the test frame. Supports optional `camera` and `group` query parameters.
- **GET /test_pattern.mjpg** – Streams a generated test pattern with a small
  spinner and multilingual timestamp overlay.

### 6. Trigger Screenshot Capture

**GET /take_screenshot/<template_name>**
**POST /take_screenshot/<template_name>**

Manually capture a screenshot for the specified template.

Appending `?motion=true` forces motion analysis for the resulting frame.

Example response:

```json
{ "status": "success", "message": "Screenshot for camera1 taken" }
```

### 7. View Status

**GET /status**

Redirects to the _System Status_ tab on the Settings page which displays metrics such as CPU, memory, and disk usage along with open file count, thread count, and uptime. These metrics are gathered in a background thread (see `app/utils/scheduling.py`).

### 8. Stream Logs

**GET /stream_logs**


Streams log records via Server-Sent Events. Optional query parameters `level`, `source`, `start_date`, `end_date`, and `search` allow filtering. The `/logs` page and _System Status_ tab use this endpoint for the live log viewer.

To reduce load during rapid typing, identical `level`/`search` combinations are ignored if a stream for the same user is already active.

Authentication is required. When a session is missing or expired the server
returns a `401` status with an SSE-formatted error message instead of redirecting
to the login page.


### 9. List Stored Videos

**GET /videos/<template_name>**

Return a JSON array of archived MP4 filenames for the specified template. Combine with `/videos/<template_name>/<filename>` to download a particular file. Filenames are validated and requests with illegal characters return `404`.

Example response:

```json
{ "videos": ["cam1_20240101.mp4", "cam1_20240102.mp4"] }
```

### 10. List Stored Screenshots

**GET /screenshots/<template_name>**

Return a JSON array of screenshot filenames for the specified template. Individual files can be downloaded via `/screenshots/<template_name>/<filename>`. Invalid filenames also return `404`.

Placeholder images created when no real screenshot is available end with `_blank.png`. The endpoint includes these names in the sorted list.

Example response:

```json
{ "screenshots": ["cam1_20240101.png", "cam1_20240102.png"] }
```

### 11. Suggest Caption Prompt

**POST /generate_prompt/<template_name>**

Analyze the latest screenshots for the template and return a short text prompt
that can be used to improve future captions.

Example response:

```json
{ "prompt": "Busy roadway — highlight license plates" }
```

### 12. Compile Teaser Video

**POST /compile_teaser**

Trigger compilation of recent footage into a teaser video. Requires authentication.
GET requests to this endpoint return `405 Method Not Allowed`.

### 13. API Discovery and Status

These utility endpoints expose basic information about the server.

**GET /api/discover**

Returns a JSON list of available endpoints with method and description.

**GET /health**

Checks the overall health of the application and returns system metrics.

**GET /danger_status**

Indicates whether Danger mode is ready for use.

**GET /captions_status**

Returns the latest caption text and timestamp.
The timestamp is now provided in ISO 8601 UTC format (e.g. `1970-01-01T00:00:00Z`).

**GET /discovery_status**

Reports the status of background camera discovery.

**GET /network_status**

Indicates whether the server is online.

### 14. Search Suggestions

**GET /search_suggestions?q=term**

Return a JSON array of camera or group names that contain the provided
query string. At most ten results are returned.

## Error Handling

All endpoints may return the following error responses:

- 400 Bad Request: Invalid parameters
- 401 Unauthorized: Invalid or missing API key
- 404 Not Found: Requested resource not found
- 500 Internal Server Error: Server-side error

For detailed integration examples and best practices, please refer to our [Developer Guide](developer_guide.md).
