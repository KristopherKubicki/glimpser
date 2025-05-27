# Glimpser API Documentation

This document outlines the API endpoints available in Glimpser for programmatic interaction with the application.

## Authentication

All API requests require an API key. Include your API key in the header of each request:

```
Authorization: Bearer YOUR_API_KEY
```

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
  "camera1": {"url": "rtsp://example"}
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
{"status": "success", "message": "Template saved"}
```
Saving a template automatically stops any scheduled job for that
camera and reschedules it using the updated parameters.

**DELETE /templates**

Remove a template by name.

Example request:
```json
{"name": "camera1"}
```
Example response:
```json
{"status": "success", "message": "Template deleted"}
```

### 2. View and Update Settings

**GET /settings**

Return the settings page in HTML format.

**POST /settings**

Submit form data to modify configuration values. A successful update redirects back to the settings page.

### 3. Stream MP4 Video

**GET /stream.mp4**

Stream the most recent MP4 video for a group. Specify `group` as a query parameter. The
video is served in small chunks and loops continuously.

Example: `/stream.mp4?group=frontdoor`

### 4. Stream Live Video

**GET /live_video**

Stream a camera directly from its configured URL in real time. Specify `camera` as a query parameter.

Example: `/live_video?camera=frontdoor`

### 5. Additional Streaming Endpoints

Several other routes provide streaming functionality:

- **GET /stream.mjpg** – Continuous MJPEG stream of the latest camera image. Optional `group` query parameter limits the feed to a group.
- **GET /stream.png** – Returns the most recent screenshot across all cameras.
- **GET /motion.mjpg** – MJPEG stream containing only motion frames. Accepts `group` as a query parameter.
- **GET /caption.mjpg** – MJPEG stream of the last caption frame for a group.
- **GET /motion_caption.mjpg** – Combines motion and caption frames in a single MJPEG stream.
- **GET /stream.m3u8** – HLS playlist referencing the latest videos from all cameras.
- **GET /last_video/<template_name>** – Download the most recent MP4 for the given template.
- **GET /last_screenshot/<template_name>** – Retrieve the latest screenshot for a template.
- **GET /last_teaser** – Returns the teaser video compiled from recent footage. Accepts an optional `group` query parameter to retrieve a group-specific teaser, e.g. `/last_teaser?group=frontdoor`.
- **GET /test.rtsp** – Basic RTSP endpoint that serves MJPEG frames when used with `/rtsp_stream`.

### 6. Trigger Screenshot Capture

**GET /take_screenshot/<template_name>**
**POST /take_screenshot/<template_name>**

Manually capture a screenshot for the specified template.

Example response:
```json
{"status": "success", "message": "Screenshot for camera1 taken"}
```

### 7. View System Status

**GET /status**

Returns an HTML dashboard displaying metrics such as CPU, memory, and disk usage along with open file count, thread count, and uptime. These metrics are gathered in a background thread (see `app/utils/scheduling.py`).

### 8. Stream Logs

**GET /stream_logs**

Streams log records via Server-Sent Events. Optional query parameters `level`, `source`, `start_date`, `end_date`, and `search` allow filtering. The `/logs` and `/status` pages use this endpoint for the live log viewer.

### 9. List Stored Videos

**GET /videos/<template_name>**

Return a JSON array of archived MP4 filenames for the specified template. Combine with `/videos/<template_name>/<filename>` to download a particular file.

Example response:
```json
{"videos": ["cam1_20240101.mp4", "cam1_20240102.mp4"]}
```

### 10. List Stored Screenshots

**GET /screenshots/<template_name>**

Return a JSON array of screenshot filenames for the specified template. Individual files can be downloaded via `/screenshots/<template_name>/<filename>`.

Example response:
```json
{"screenshots": ["cam1_20240101.png", "cam1_20240102.png"]}
```

## Error Handling

All endpoints may return the following error responses:

- 400 Bad Request: Invalid parameters
- 401 Unauthorized: Invalid or missing API key
- 404 Not Found: Requested resource not found
- 500 Internal Server Error: Server-side error

For detailed integration examples and best practices, please refer to our [Developer Guide](developer_guide.md).
