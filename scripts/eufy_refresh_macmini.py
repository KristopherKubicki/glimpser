#!/usr/bin/env python3
"""Refresh newer verified Eufy frames through the normal capture pipeline."""

import argparse
import time
from datetime import datetime, timezone


def needs_refresh(device, template, now):
    """Never redate stale, failed or already imported bridge artifacts."""
    if not device.get("capture_enabled", True) or device.get("status") != "captured":
        return False
    snapshot = device.get("snapshot")
    if not isinstance(snapshot, dict):
        return False
    try:
        source_time = float(snapshot.get("mtime_epoch", 0))
        if not 0 <= now - source_time <= 16 * 3600:
            return False
        recorded = str(template.get("last_screenshot_time") or "")
        previous = (
            datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            if recorded
            else None
        )
        if previous and previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        return previous is None or source_time > previous.timestamp()
    except (TypeError, ValueError):
        return False


def main(profile_name: str) -> None:
    """Refresh only an explicitly selected, configured external bridge profile."""
    from app.utils import eufy_cloud, scheduling, template_manager

    profile_name = profile_name.strip().lower()
    if not profile_name:
        raise ValueError("Refresh requires an explicit bridge profile")
    profile = eufy_cloud.resolve_profile(profile_name)
    if not profile or profile.mode != "external":
        raise ValueError("Refresh requires a configured external bridge profile")
    # Reuse the bridge client so authentication, TLS policy and timeout handling
    # match normal capture. An unavailable bridge yields no importable frames.
    devices = {
        str(device.get("device_id") or device.get("id") or ""): device
        for device in eufy_cloud._external_bridge_devices(profile, timeout=8)
    }
    for name, template in template_manager.get_templates().items():
        url = str(template.get("url", ""))
        if not url.startswith("eufy://"):
            continue
        source_profile, device_id = eufy_cloud.parse_eufy_url(url)
        if source_profile != profile_name:
            continue
        if not needs_refresh(devices.get(device_id, {}), template, time.time()):
            print(
                name, "no newer verified frame; existing capture preserved", flush=True
            )
            continue
        # Normal capture maintains clean/latest links and deduplicates unchanged
        # images; the old first-pass helper unconditionally stamped them as new.
        scheduling.update_camera(name, template)
        print(name, "normal capture attempted; consult capture status", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", required=True, help="Configured external bridge profile"
    )
    main(parser.parse_args().profile)
