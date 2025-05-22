#!/usr/bin/env python3
"""Check for system dependencies required by Glimpser."""

import shutil

REQUIRED = ["google-chrome", "ffmpeg"]

missing = [cmd for cmd in REQUIRED if shutil.which(cmd) is None]

if missing:
    print("Missing dependencies: " + ", ".join(missing))
else:
    print("All required dependencies found.")
