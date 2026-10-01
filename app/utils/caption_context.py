"""Read-only, time-aligned device evidence for household camera captions."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from app.household_config import load_household_config

MARKER = "[household-context-v1]"
HOUSEHOLD = load_household_config()
HUB_URL = HOUSEHOLD.get("hub_url", "")
VEHICLE = HOUSEHOLD.get("vehicle_caption", {})


def _timestamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
    except (ValueError, TypeError):
        return None


def _read_states(device):
    if not HUB_URL or not VEHICLE:
        return {}
    try:
        with urlopen(f"{HUB_URL}/device/fullJson/{device}", timeout=3) as response:
            states = json.load(response).get("device", {}).get("currentStates", {})
        # Project immediately: never pass preferences, VIN, tokens or GPS to the LLM.
        allowed = (
            {"chargingState", "pluggedIn", "chargePowerKw", "battery"}
            if device == VEHICLE.get("device")
            else {"presence", "lastUpdated"}
        )
        return {
            key: {"value": val.get("value"), "date": val.get("date")}
            for key, val in states.items()
            if key in allowed and isinstance(val, dict)
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def vehicle_evidence(states, network, captured, now):
    """Return only evidence recent both now and at the photographed moment."""

    def aligned(value):
        stamp = _timestamp(value)
        return bool(
            stamp
            and 0 <= (now - stamp).total_seconds() <= 300
            and abs((stamp - captured).total_seconds()) <= 120
        )

    evidence = []
    if not 0 <= (now - captured).total_seconds() <= 300:
        return evidence
    for key in ("chargingState", "pluggedIn", "chargePowerKw", "battery"):
        item = states.get(key, {})
        value = item.get("value")
        if aligned(item.get("date")) and isinstance(value, (str, int, float, bool)):
            evidence.append(
                {
                    "device": VEHICLE.get("device", ""),
                    "attribute": key,
                    "value": str(value)[:80],
                    "reported_at": item["date"],
                }
            )
    presence = network.get("presence", {}).get("value")
    heartbeat = network.get("lastUpdated", {}).get("date")
    if aligned(heartbeat) and presence in {"present", "not present"}:
        evidence.append(
            {
                "device": VEHICLE.get("network_device", ""),
                "attribute": "networkPresence",
                "value": presence,
                "verified_at": heartbeat,
            }
        )
    return evidence


def caption_context(name, image_paths, now=None):
    """Link the known driveway vehicle without confusing telemetry with vision."""
    if str(name or "").startswith("Hubitat"):
        region = (
            "[main-device-region-v1] Only the bottom device-card region is supplied; "
            "embedded camera thumbnails are excluded from analysis. "
            if name == "HubitatMain"
            else ""
        )
        return region + (
            f"\n{MARKER}\nDashboard interpretation: summarize only explicitly readable "
            "device values, errors and states. Do not recaption embedded camera or TV "
            "thumbnails: each camera has its own caption and thumbnail text may be old. "
            "Do not infer activity, vehicle identity, occupancy or damage from those "
            "thumbnails. Do not interpret tile colors or icons as state if no readable "
            "state value supports it. Labels such as Ghost or plug-in are names, "
            "not faults or power states. Keep at most three useful findings."
        )
    if not HUB_URL or not VEHICLE or name != VEHICLE["camera"]:
        return ""
    prefix = f"\n{MARKER}\n{VEHICLE['facts']}\n"
    stamps = []
    for path in image_paths:
        match = re.fullmatch(
            rf"{re.escape(VEHICLE['camera'])}_(\d{{14}})\.png(?:\.clean\.png)?",
            Path(path).name,
        )
        if match:
            try:
                stamps.append(
                    datetime.strptime(match[1], "%Y%m%d%H%M%S").replace(
                        tzinfo=timezone.utc
                    )
                )
            except ValueError:
                continue
    now = now or datetime.now(timezone.utc)
    if not stamps or not 0 <= (now - max(stamps)).total_seconds() <= 300:
        return (
            prefix
            + "No contemporaneous telemetry: do not describe current charging or presence from device history."
        )
    captured = max(stamps)
    evidence = vehicle_evidence(
        _read_states(VEHICLE["device"]),
        _read_states(VEHICLE["network_device"]),
        captured,
        now,
    )
    return prefix + (
        f"Linked read-only Hubitat devices: {VEHICLE['device']} = {VEHICLE['label']}; "
        f"{VEHICLE['network_device']} = vehicle network presence (not GPS or visual identification). "
        f"Evidence aligned to newest image, captured {captured.isoformat()}: "
        + json.dumps(evidence, sort_keys=True)
        + ". Attribute device facts to Hubitat; never claim they were seen in the image. "
        "Missing fields are unknown, not off. Network presence does not establish the "
        "vehicle's exact parking location. Contradictions remain uncertain. "
        "Never use phone or household presence to identify a photographed person. "
        "Do not repeat instructions or unavailable telemetry in the caption."
    )
