# Google Home WEB_RTC Support

Glimpser now supports importing SDM cameras that advertise `WEB_RTC` (not just `RTSP`).

## What Changed

- SDM imports now allow camera/doorbell devices with `WEB_RTC`.
- `sdm://<profile>/<device_id>` captures now:
  - try RTSP first,
  - fall back to a signed local WebRTC preview route when the device is WEB_RTC-only.
- New SDM WebRTC signaling endpoints were added for browser offer/answer and session keepalive.

## Operational Notes

- This keeps Glimpser self-contained: snapshots are generated through local headless Chrome.
- Preview access can be authenticated by login or short-lived signed token.
- If SDM rejects WebRTC start/extend/stop commands, check:
  - profile OAuth + refresh token,
  - project/device binding in Google Device Access,
  - camera permissions for the linked account.
