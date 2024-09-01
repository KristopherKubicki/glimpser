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

## Error Handling

All endpoints may return the following error responses:

- 400 Bad Request: Invalid parameters
- 401 Unauthorized: Invalid or missing API key
- 404 Not Found: Requested resource not found
- 500 Internal Server Error: Server-side error

For detailed integration examples and best practices, please refer to our [Developer Guide](developer_guide.md).