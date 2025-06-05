# System Monitoring and Logs

This guide explains how to check Glimpser's health metrics and view live logs.

## System Status Endpoint

**GET /status**

This endpoint now redirects to the _System Status_ tab on the Settings page. The tab shows current system metrics and includes the live log viewer. Metrics are collected in a background thread. See `app/utils/scheduling.py` for implementation details. Raw values can also be retrieved programmatically from the `/health` endpoint. The metrics list and feed dashboard are grouped into separate cards for a cleaner layout. CPU, memory, and disk usage display small progress bars for a quick visual indicator.

### Feed Dashboard

Below the system metrics the page lists each configured feed with a color-coded indicator. Hovering over a red or yellow dot now shows a short tooltip describing the issue, including when the feed went offline and the most recent related log entry if available.

- **Green** – the feed is updating on schedule.
- **Yellow** – the last capture is behind its configured frequency.
- **Red** – capturing failed or the feed is offline.

The dashboard also shows when the most recent system summary was generated.

Additional KPI columns track the number of screenshots, videos, total storage
used, LLM responses, and estimated LLM cost for each feed.

The table headers are sortable. Click a column name to reorder feeds by feed
name, last image time, last caption time, any KPI column, or status.

### Metrics

- **CPU Usage** – percentage of CPU time used by the process
- **Memory Usage** – percentage of system memory in use
- **Disk Usage** – percentage of disk space used on the main volume
- **Open Files** – number of file descriptors opened by the process
- **Thread Count** – active thread count for the application
- **Uptime** – elapsed time since the app started
- **FFmpeg Version** – version string reported by the ffmpeg binary
- **Machine HW Accel** – whether GPU devices are detected
- **FFmpeg HW Accel** – whether ffmpeg supports hardware acceleration
- **HW Accel Enabled** – if hardware acceleration is configured

## Streaming Logs

**GET /stream_logs**

This endpoint delivers log entries using Server‑Sent Events. Optional query parameters allow filtering by level, source, date range, and text search. The `/logs` page and the _System Status_ tab consume this endpoint to display updates in real time.

To filter logs by level and message text, you could request:

```
/stream_logs?level=INFO&search=camera
```

## Using the Live Log Viewer

1. Open the _System Status_ tab under Settings or navigate to `/logs` after logging in.
2. Use the search box and dropdowns to filter log output.
3. Hover over each field for a tooltip explaining the filter.
4. Results update automatically via `/stream_logs`.
5. If the connection drops, the viewer automatically reconnects after a few seconds and shows a short notice while retrying.

The log viewer reads log lines from memory, ensuring minimal disk overhead.

The _System Status_ tab also appears as a **System Status** camera under Discover.
Adding it lets Glimpser capture periodic screenshots of its own health metrics.
An accompanying **Internal Caption** camera shows `/internal_caption.mjpg` so you
can monitor recent caption text without leaving the dashboard.

## Caption Activity Indicator

The navigation bar shows a captions icon that reflects how recent the last
caption update was. When viewing a group or individual camera page the icon uses
the newest caption from that group. It flashes with the newest caption text when
a group message arrives. After a few seconds of inactivity the latest global summary slowly
scrolls across the top in a gray chyron. Clicking this text opens the `/captions`
page for more
details. The scroll duration comes from the `CHYRON_SPEED` setting which is
`0` by default to disable the banner. The icon remains green for one minute
after a caption, changes to
yellow for the next five minutes and turns red once thirty minutes have passed
without an update.
You can toggle the chyron from the **Captions** page using the button in the
History tab.

## System Performance Icon

The System Performance icon in the navigation bar provides quick access to the
_System Status_ tab. When all metrics look healthy the icon now hides to reduce
clutter. Set the `HEALTH_STATUS_ALWAYS_VISIBLE` option to `True` if you prefer
to keep it shown at all times.

## Danger Mode Indicator

When Chrome's remote debugging port is open and no user input has been detected for a short time, an orange icon appears in the navigation bar. The icon hides again when Danger mode is unavailable. Hovering over it explains why Danger mode may be disabled. See [Danger Mode](danger_mode.md) for setup instructions.

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
