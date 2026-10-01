"""Validate private kiosk preferences while retaining usable generic presets."""

import copy
import json
import logging
import math
import os
from pathlib import Path

from app.landing_defaults import DEFAULTS


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError("Invalid landing text")
    return value.strip()


def _names(value):
    if not isinstance(value, list) or len(value) > 1024:
        raise ValueError("Expected bounded list")
    return [_text(item) for item in value]


def _number(value, minimum=-1000, maximum=1000, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum <= value <= maximum
        or not math.isfinite(value)
        or (integer and not isinstance(value, int))
    ):
        raise ValueError("Invalid landing number")
    return value


def _mapping(value, validator):
    if not isinstance(value, dict) or len(value) > 1024:
        raise ValueError("Expected bounded mapping")
    return {_text(key): validator(item) for key, item in value.items()}


def _profile(key, values):
    if not isinstance(values, dict):
        raise ValueError("Invalid profile")
    result = {}
    for name, value in values.items():
        if name in {"key", "label", "short_label"}:
            result[name] = _text(value)
        elif name == "all_eligible":
            if not isinstance(value, bool):
                raise ValueError("Expected boolean")
            result[name] = value
        elif name in {"rotation_ms", "max_rotation_ms"}:
            result[name] = _number(value, 1000, 3600000, integer=True)
        elif name in {"scene_size_bonus", "max_scenes_bonus"}:
            result[name] = _number(value, 0, 200, integer=True)
        elif name in {
            "scene_size",
            "max_scenes",
            "scene_window_size",
            "scene_chunk_stride",
            "max_group_scenes",
        }:
            result[name] = _number(value, 1, 200, integer=True)
        elif name in {
            "lane_fill_order",
            "lane_minimums",
            "camera_minimums",
            "group_minimums",
            "distributed_groups",
        }:
            result[name] = _names(value)
        elif name == "lane_bias":
            result[name] = _mapping(value, _number)
        elif name in {"group_scene_caps", "group_window_sizes"}:
            result[name] = _mapping(value, lambda v: _number(v, 1, 200, integer=True))
        elif name == "group_rotation_multipliers":
            result[name] = _mapping(value, lambda v: _number(v, 0.1, 10))
        else:
            raise ValueError("Unknown profile setting")
    if (
        result.get("key") != key
        or not {"label", "short_label", "max_scenes", "scene_size"} <= result.keys()
    ):
        raise ValueError("Incomplete profile")
    return result


def load_landing_config() -> dict:
    """Load bounded private JSON at startup, falling back atomically on invalid data."""
    defaults = copy.deepcopy(DEFAULTS)
    path = os.getenv("GLIMPSER_LANDING_CONFIG", "").strip()
    if not path:
        return defaults
    try:
        with Path(path).expanduser().open(encoding="utf-8") as stream:
            raw = stream.read(262145)
        if len(raw) > 262144:
            raise ValueError("Landing configuration too large")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.keys() - defaults.keys():
            raise ValueError("Unknown landing configuration")
        for key, value in data.items():
            if key == "LANDING_CONTENT_PROFILES":
                if (
                    not isinstance(value, dict)
                    or not value
                    or value.keys() - defaults[key].keys()
                ):
                    raise ValueError("Unknown profile")
                defaults[key].update({k: _profile(k, v) for k, v in value.items()})
            elif key in {"LANDING_GROUP_BONUSES", "LANDING_NAME_PENALTIES"}:
                defaults[key] = _mapping(value, _number)
            elif key in {"LANDING_LANE_HINTS", "LANDING_PROFILE_EXCLUDED_CAMERAS"}:
                defaults[key] = _mapping(value, _names)
            elif key in {"LANDING_HOST_PROFILE_HINTS", "LANDING_HOST_MODE_HINTS"}:
                if not isinstance(value, list) or len(value) > 128:
                    raise ValueError("Invalid host hints")
                allowed = (
                    set(defaults["LANDING_CONTENT_PROFILES"])
                    if key == "LANDING_HOST_PROFILE_HINTS"
                    else {"low", "medium", "high", "ultra"}
                )
                hints = []
                for pair in value:
                    pair = _names(pair)
                    if len(pair) != 2 or pair[1] not in allowed:
                        raise ValueError("Invalid host mapping")
                    hints.append([pair[0].lower(), pair[1]])
                defaults[key] = hints
            else:
                defaults[key] = _names(value)
        return defaults
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logging.warning("Invalid landing configuration; using generic kiosk presets")
        return copy.deepcopy(DEFAULTS)
