"""Administrator opt-in daylight window for inferred-color display derivatives."""

import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

POLICY = Path.home() / ".config/glimpser/colorization-policy.json"


def eligible(camera, captured_at, path=POLICY):
    """Fail closed. Explicit conservative local-hour windows, never inferred sun."""
    try:
        if type(captured_at) not in (int, float) or not math.isfinite(captured_at):
            return False
        if path.is_symlink() or path.stat().st_size > 65536:
            return False
        config = json.loads(path.read_text())
        if config.get("version") != 1:
            return False
        rule = config.get("cameras", {}).get(camera, {})
        start, end = rule["daylight_hours"]
        if rule.get("enabled") is not True or not 0 <= start < end <= 24:
            return False
        local = dt.datetime.fromtimestamp(captured_at, tz=ZoneInfo(rule["timezone"]))
        return start <= local.hour + local.minute / 60 < end
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        ZoneInfoNotFoundError,
    ):
        return False
