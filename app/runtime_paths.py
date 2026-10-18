"""Choose durable runtime storage independently of frozen bundle extraction."""

import os
import sys
from pathlib import Path


def application_state_root(config_file: str) -> Path:
    """Keep frozen-app data outside PyInstaller's temporary extraction directory."""
    if getattr(sys, "frozen", False):
        return (
            Path(os.environ.get("GLIMPSER_STATE_DIR") or Path.home() / ".glimpser")
            .expanduser()
            .resolve()
        )
    return Path(config_file).resolve().parent.parent
