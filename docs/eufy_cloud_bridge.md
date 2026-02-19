# Eufy Cloud Cameras

Glimpser supports first-class Eufy cloud imports with two enclosed modes:

- Templates are stored as `eufy://<profile>/<device_id>`.
- At capture time Glimpser converts these URLs into signed local proxy URLs:
  `/integrations/eufy/snapshot?...`.
- The proxy fetches snapshots from either native Eufy cloud auth or your
  configured bridge endpoint.

This keeps credentials and cloud tokens server-side in Glimpser.

## Configure

1. Open **Settings -> Eufy Cloud Cameras -> Open Eufy Integration**.
2. Create a profile (for example `argyle`, `beach`, `halsted`).
3. Choose mode:
   - `Native Cloud (no bridge endpoint)`:
     - Fill `Eufy Account Email` + `Eufy Account Password`.
     - Optional: set `Eufy Country Code` (default `US`).
   - `External Bridge`:
     - Fill `Bridge URL` (for example `http://127.0.0.1:18888`)
     - `Devices Path` (default: `/api/devices`)
     - `Snapshot Path` (default: `/api/cameras/{device_id}/snapshot`)
     - `API Token` (optional, bridge-specific)
4. Set `Verify TLS` (enable for trusted HTTPS bridges).
5. Save profile.
6. Click **Discover / Import Cameras**.
7. Select cameras and import them into a group.

## Bridge API shape

`Devices Path` should return JSON with one of:

- a list of objects, or
- an object containing one of `devices`, `cameras`, `data`, or `items`.

Each device object should include an ID field such as:

- `device_id`, `id`, `serialNumber`, or `serial`.

Snapshot endpoint responses supported by Glimpser:

- direct image bytes (`Content-Type: image/*`),
- JSON with base64 image (`image_base64`, `snapshot_base64`, `jpeg_base64`), or
- JSON redirect URL (`snapshot_url`, `image_url`, `url`).

## Notes

- Native mode is screenshot-focused by design (thumbnail-style cloud captures,
  not 4K live transcoding).
- Use a dedicated Eufy guest account for automation when possible.
- If a bridge is slow/unavailable, the template will back off and retry on normal
  capture schedule.
