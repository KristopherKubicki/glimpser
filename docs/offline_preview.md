# Offline Preview

A simple Service Worker allows Glimpser to keep showing recent images when the network is spotty. The browser automatically registers `/sw.js`, which caches the dashboard (`/`), the System Status tab (`/settings?tab=status-tab`), the main Settings page, and the Templates page (including the Discover tab). Key stylesheets and scripts are stored as well, along with the most recent 20 snapshot images. If fetching a new image fails or returns a 504 error, the cached copy is displayed instead so the player does not show a blank pane.

Requests now time out after five seconds so the UI quickly falls back to the cached pages when the server is slow or restarting.

MJPEG endpoints now fall back to the oldest frame stored on disk if no recent frame is available. This means `/stream.mjpg` and related routes always yield at least one image even when the camera is offline.

The interface polls `/network_status` every 10 seconds. When the request fails
or reports the system is offline, a banner appears below the navigation bar to
indicate Glimpser is running in offline mode. The banner has the
`network-banner` class and is hidden until the `show` class is added. It
disappears automatically once connectivity is restored.

Navigation requests that miss the cache now fall back to `/offline`, so users
see a friendly message instead of a blank page when connectivity drops.
