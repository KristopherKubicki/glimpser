"""Export per-camera PNGs from a stable multi-camera Eufy app view.

This is the missing local step for the Mac mini bridge pattern:

1. capture one stable Eufy app window or screen region
2. crop named ROIs for each camera tile
3. write one PNG per camera

The external bridge can then serve those PNGs directly via ``snapshot_path``.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image


def load_exporter_config(path: str | Path) -> dict[str, Any]:
    """Load exporter JSON config."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Exporter config must be a JSON object.")
    return payload


def parse_roi(roi: str, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Return a pixel ROI from either normalized or pixel coordinates."""

    text = str(roi or "").strip()
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI must have exactly four comma-separated values.")

    values = [float(part) for part in parts]
    width, height = image_size
    if max(values) <= 1.0:
        x = int(round(values[0] * width))
        y = int(round(values[1] * height))
        w = int(round(values[2] * width))
        h = int(round(values[3] * height))
    else:
        x, y, w, h = [int(round(value)) for value in values]

    if w <= 0 or h <= 0:
        raise ValueError("ROI width and height must be positive.")

    left = max(0, min(x, width))
    top = max(0, min(y, height))
    right = max(left + 1, min(x + w, width))
    bottom = max(top + 1, min(y + h, height))
    return left, top, right, bottom


def _render_capture_command(command: str, output_path: Path) -> list[str]:
    """Render a capture command, replacing ``{output}`` when present."""

    rendered = str(command or "").strip()
    if not rendered:
        raise ValueError("capture_cmd is required when source_image_path is empty.")

    if "{output}" in rendered:
        rendered = rendered.replace("{output}", str(output_path))
        return shlex.split(rendered)

    args = shlex.split(rendered)
    args.append(str(output_path))
    return args


def capture_source_image(config: dict[str, Any]) -> Path:
    """Capture or resolve the current source image path."""

    source_image_path = str(config.get("source_image_path") or "").strip()
    if source_image_path:
        path = Path(source_image_path)
        if not path.exists():
            raise FileNotFoundError(f"source_image_path not found: {path}")
        return path

    capture_cmd = str(config.get("capture_cmd") or "").strip()
    timeout = max(1.0, float(config.get("capture_timeout_seconds") or 8.0))
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    args = _render_capture_command(capture_cmd, tmp_path)
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(stderr or f"Capture command failed: {result.returncode}")
        if not tmp_path.exists():
            raise FileNotFoundError(
                f"Capture command completed but did not create {tmp_path}"
            )
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def export_device_crops(source_path: Path, devices: list[dict[str, Any]]) -> int:
    """Write one cropped PNG per device from the source image."""

    written = 0
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        for device in devices:
            snapshot_path = str(device.get("snapshot_path") or "").strip()
            roi = str(device.get("roi") or "").strip()
            if not snapshot_path or not roi:
                continue

            crop_box = parse_roi(roi, image.size)
            cropped = image.crop(crop_box)
            target = Path(snapshot_path)
            target.parent.mkdir(parents=True, exist_ok=True)

            # Write to a temp file first so the bridge never serves partial PNGs.
            with tempfile.NamedTemporaryFile(
                suffix=target.suffix or ".png",
                dir=str(target.parent),
                delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)
            try:
                cropped.save(tmp_path, format="PNG")
                tmp_path.replace(target)
                written += 1
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
    return written


def run_once(config: dict[str, Any]) -> int:
    """Capture one source image and export all configured device crops."""

    source_path = capture_source_image(config)
    try:
        devices = config.get("devices")
        if not isinstance(devices, list):
            raise ValueError("devices must be a list.")
        return export_device_crops(source_path, devices)
    finally:
        if not str(config.get("source_image_path") or "").strip():
            source_path.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to exporter JSON config.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one export pass and exit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)
    config = load_exporter_config(args.config)
    interval = max(1.0, float(config.get("interval_seconds") or 5.0))

    if args.once:
        print(f"Exported {run_once(config)} camera crops")
        return 0

    while True:
        written = run_once(config)
        print(f"Exported {written} camera crops")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
