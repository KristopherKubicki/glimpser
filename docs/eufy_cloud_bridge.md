# Eufy Cameras (ADB-Only)

Glimpser supports enclosed Eufy imports with VM/emulator mode:

- Templates are stored as `eufy://<profile>/<device_id>`.
- At capture time Glimpser resolves these URLs through its signed local
  `/integrations/eufy/snapshot` proxy and captures from ADB.

## Configure

1. Open **Settings -> Eufy Cloud Cameras -> Open Eufy Integration**.
2. Create a profile (for example `argyle`, `beach`, `halsted`).
3. Mode is deployment-locked to `VM / Emulator (ADB)`:
   - Fill `Emulator Device Catalog (JSON)` with one row per camera.
   - Optional: set `Emulator ADB Path` when `adb` is not on system `PATH`.
   - Optional: set `Emulator ADB Serial` for multi-device hosts.
   - Optional: set `Emulator Launch Cmd` to open a camera before capture.
     Placeholders supported: `{profile}`, `{device_id}`, `{device_name}`, `{deep_link}`.
   - Optional: set `Emulator Capture Cmd` (defaults to `adb exec-out screencap -p`).
   - Set `Emulator Settle Seconds` to wait before taking each frame.
4. Optional: set `Emulator Boot Command` to let Glimpser start the VM when ADB
   has no device (for example `virsh start android-vm`).
   - If empty, Glimpser tries auto-detection (`GLIMPSER_EUFY_BOOT_CMD`,
     libvirt `virsh`, Waydroid, then Android SDK `emulator`).
5. Optional: set `Emulator Boot Timeout (seconds)` for slower boots.
6. Save profile.
7. Click **Discover / Import Cameras**.
8. Select cameras and import them into a group.
9. On the Eufy devices page, click **Run First Pass Now** (or keep
   **Capture first screenshot after import** enabled) to seed initial frames
   without waiting for scheduler cadence.

## Notes

- VM / Emulator mode is screenshot-focused; it captures whatever is visible in
  the Android VM/app when the capture command runs.
- Web/native/API capture paths are disabled in this deployment.
- Use a dedicated Eufy guest account for automation when possible.
- If a bridge is slow/unavailable, the template will back off and retry on normal
  capture schedule.

## Emulator Device Catalog Example

`Emulator Device Catalog (JSON)` accepts a list or a `devices` object:

```json
{
  "devices": [
    {
      "device_id": "T81A0P10242844B3",
      "name": "Driveway",
      "deep_link": "eufysecurity://camera/T81A0P10242844B3"
    },
    {
      "device_id": "T8171T1024520486",
      "name": "Bioswale"
    }
  ]
}
```

## First-Pass Snapshot Script

After captcha is solved, you can force a one-time pass over imported Eufy templates:

```bash
uv run python scripts/eufy_first_pass.py --profile default --interactive
```

Or provide the captcha directly:

```bash
uv run python scripts/eufy_first_pass.py --profile default --captcha-code 1234 --json
```

The script writes PNGs into each camera folder under `SCREENSHOT_DIRECTORY` and
updates template capture status/timestamps.
