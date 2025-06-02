# System Monitoring and Logs

This guide explains how to check Glimpser's health metrics and view live logs.

## System Status Endpoint

**GET /status**

The status page shows current system metrics and includes the live log viewer. Metrics are collected in a background thread. See `app/utils/scheduling.py` for implementation details. Raw values can also be retrieved programmatically from the `/health` endpoint.

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
3. Hover over each field for a tooltip explaining the filter.
4. Results update automatically via `/stream_logs`.

The log viewer reads log lines from memory, ensuring minimal disk overhead.

## Persistent Log Storage

All log entries are also written to the `logs` table in the SQLite database. You
can inspect them directly:

```bash
sqlite3 data/glimpser.db "SELECT level, source, message FROM logs ORDER BY id DE
SC LIMIT 10;"
```

This table is created automatically when the application starts.

The `/status` page also appears on the `/discover` screen as a **System Status**
camera. Adding it lets Glimpser capture periodic screenshots of its own health
metrics.

## Danger Mode Indicator

When Chrome's remote debugging port is open and no user input has been detected for a short time, Danger mode becomes available. An orange dot in the navigation bar shows this state. Hovering over the dot explains why Danger mode may be unavailable. See [Danger Mode](danger_mode.md) for setup instructions.

## Profiling

Each profiled API request writes its execution time to `data/latency_log.json`.
Query aggregated averages and counts using the `/profiling` endpoint:

```bash
curl /profiling
```

Use this information to identify slow endpoints and monitor performance.


Baseline metrics from the main branch are stored in
`docs/latency_baseline.json`. Run the helper script to refresh this file after
tests:

```bash
python scripts/update_latency_baseline.py
```

CI bots can compare the latest profiling results against this baseline to detect
latency regressions.

