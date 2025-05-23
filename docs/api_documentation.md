# Glimpser API Documentation

This document outlines the API endpoints available in Glimpser for programmatic interaction with the application.

## Authentication

All API requests require an API key. Include your API key in the header of each request:

```
Authorization: Bearer YOUR_API_KEY
```

## Endpoints

### 1. List Data Sources

**GET /api/v1/sources**

Retrieves a list of all configured data sources.

Response:
```json
{
  "sources": [
    {
      "id": "source_id",
      "name": "Source Name",
      "type": "camera",
      "url": "http://example.com/camera1"
    },
    ...
  ]
}
```

### 2. Add Data Source

**POST /api/v1/sources**

Adds a new data source to Glimpser.

Request Body:
```json
{
  "name": "New Camera",
  "type": "camera",
  "url": "http://example.com/new_camera",
  "refresh_rate": 60
}
```

Response:
```json
{
  "id": "new_source_id",
  "name": "New Camera",
  "type": "camera",
  "url": "http://example.com/new_camera",
  "refresh_rate": 60
}
```

### 3. Get Latest Data

**GET /api/v1/data/{source_id}**

Retrieves the latest data from a specific source.

Response:
```json
{
  "source_id": "source_id",
  "timestamp": "2023-06-15T14:30:00Z",
  "data": {
    "image_url": "http://example.com/latest_image.jpg",
    "caption": "A busy intersection with cars and pedestrians",
    "summary": "Traffic appears normal with moderate vehicle and foot traffic"
  }
}
```

### 4. Get Summary

**GET /api/v1/summary**

Retrieves a summary of recent data across all sources.

Response:
```json
{
  "timestamp": "2023-06-15T14:35:00Z",
  "summary": "Overall, traffic conditions are normal across monitored areas. Weather remains clear with no significant events detected."
}
```

### 5. Manage Templates

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

### 6. View and Update Settings

**GET /settings**

Return the settings page in HTML format.

**POST /settings**

Submit form data to modify configuration values. A successful update redirects back to the settings page.

### 7. Stream MP4 Video

**GET /stream.mp4**

Stream the most recent MP4 video for a group. Specify `group` as a query parameter. The
video is served in small chunks and loops continuously.

Example: `/stream.mp4?group=frontdoor`

### 8. Stream Live Video

**GET /live_video**

Stream a camera directly from its configured URL in real time. Specify `camera` as a query parameter.

Example: `/live_video?camera=frontdoor`

### 9. Trigger Screenshot Capture

**GET /take_screenshot/<template_name>**
**POST /take_screenshot/<template_name>**

Manually capture a screenshot for the specified template.

Example response:
```json
{"status": "success", "message": "Screenshot for camera1 taken"}
```

## Error Handling

All endpoints may return the following error responses:

- 400 Bad Request: Invalid parameters
- 401 Unauthorized: Invalid or missing API key
- 404 Not Found: Requested resource not found
- 500 Internal Server Error: Server-side error

For detailed integration examples and best practices, please refer to our [Developer Guide](developer_guide.md).
