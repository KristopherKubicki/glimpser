# Offline Preview

A simple Service Worker allows Glimpser to keep showing recent images when the network is spotty. When **Enable offline preview** is checked on the Settings page, the browser registers `/sw.js` which caches the `/status` and `/discover` pages along with the most recent 20 snapshot images. If fetching a new image fails or returns a 504 error, the cached copy is displayed instead so the player does not show a blank pane.

MJPEG endpoints now fall back to the oldest frame stored on disk if no recent frame is available. This means `/stream.mjpg` and related routes always yield at least one image even when the camera is offline.
