#!/usr/bin/env python3
"""Print a camera capture health report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY  # noqa: E402
from app.utils.camera_health import (  # noqa: E402
    build_camera_health_report,
    format_camera_health_report,
)
from app.utils.template_manager import get_templates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--include-healthy", action="store_true")
    parser.add_argument("--include-archived", action="store_true")
    args = parser.parse_args()

    report = build_camera_health_report(
        get_templates(),
        screenshot_dir=SCREENSHOT_DIRECTORY,
        video_dir=VIDEO_DIRECTORY,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            format_camera_health_report(
                report,
                limit=args.limit,
                include_healthy=args.include_healthy,
                include_archived=args.include_archived,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
