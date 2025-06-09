# Telemetry

The interface now records lightweight usage events. When you test a URL or submit the template form,
a small JSON payload is POSTed to `/telemetry`. The server keeps the last
1000 events in memory and logs them for diagnostics.
