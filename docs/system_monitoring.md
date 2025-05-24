# System Monitoring and Logs

This guide explains how to check Glimpser's health metrics and view live logs.

## System Status Endpoint

**GET /status**

The status page shows current system metrics and includes the live log viewer. Metrics are collected in a background thread. See `app/utils/scheduling.py` for implementation details.

### Metrics

- **CPU Usage** – percentage of CPU time used by the process
- **Memory Usage** – percentage of system memory in use
- **Disk Usage** – percentage of disk space used on the main volume
- **Open Files** – number of file descriptors opened by the process
- **Thread Count** – active thread count for the application
- **Uptime** – elapsed time since the app started

## Streaming Logs

**GET /stream_logs**

This endpoint delivers log entries using Server‑Sent Events. Optional query parameters allow filtering by level, source, date range, and text search. The `/logs` and `/status` pages consume this endpoint to display updates in real time.

To filter logs by level and message text, you could request:

```
/stream_logs?level=INFO&search=camera
```

## Using the Live Log Viewer

1. Navigate to `/status` or `/logs` after logging in.
2. Use the search box and dropdowns to filter log output.
3. Results update automatically via `/stream_logs`.

The log viewer reads log lines from memory, ensuring minimal disk overhead.
