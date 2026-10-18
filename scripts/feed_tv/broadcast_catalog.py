"""Explicit local OTA catalog updates; no credentials or channel discovery writes."""

from scripts.media_config import load_media_config

CHANNELS = {"WBBM-TV": "2.1", "WMAQ": "5.1", "WLS": "7.1", "WGN": "9.1", "WFLD": "32.1"}


def updates(rows):
    """Plan only matching tuner sources, preserving faster operator cadences."""
    host = load_media_config().get("tuner_host")
    if not host:
        return {}
    result = {}
    for name, channel in CHANNELS.items():
        url = f"http://{host}:5004/auto/v{channel}"
        old = rows.get(name)
        if old is None:
            if name != "WLS":
                continue
            result[name] = {
                "url": url,
                "groups": "tv",
                "frequency": 15,
                "timeout": 45,
                "browser": False,
                "invert": False,
                "notes": "ABC 7 Chicago OTA broadcast. Attribute claims to the broadcast. Distinguish news, replay, entertainment and advertisements. A captured frame is not proof of current breaking news.",
            }
        elif old["url"] != url:
            raise ValueError("broadcast_source_changed:" + name)
        elif float(old.get("frequency") or 60) > 15:
            result[name] = {"frequency": 15}
    return result
