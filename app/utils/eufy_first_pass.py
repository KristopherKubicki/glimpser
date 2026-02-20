"""Run a one-time first-pass capture for imported Eufy templates."""

from __future__ import annotations

import datetime
import io
import os
from typing import Any, Iterable

from PIL import Image

from app.config import SCREENSHOT_DIRECTORY
from app.utils import eufy_cloud, screenshots, template_manager


def _save_snapshot_png(*, name: str, payload: bytes, invert: bool) -> str:
    """Save raw image bytes as a timestamped PNG and add standard overlays."""

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    camera_dir = os.path.join(SCREENSHOT_DIRECTORY, name)
    os.makedirs(camera_dir, exist_ok=True)
    output_path = os.path.join(camera_dir, f"{name}_{timestamp}.png")

    with Image.open(io.BytesIO(payload)) as img:
        img = img.convert("RGB")
        img.save(output_path, "PNG")

    screenshots.add_timestamp(output_path, name=name, invert=invert)
    return output_path


def capture_profile_first_pass(
    profile: str, *, timeout: float = 20.0, template_names: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Capture one snapshot for imported ``eufy://`` templates in ``profile``.

    Returns a result row per targeted template with keys:
    ``name``, ``profile``, ``device_id``, ``ok``, ``file``, ``error``.
    """

    clean_profile = str(profile or "").strip().lower() or "default"
    selected_names = set(str(name) for name in (template_names or []) if str(name))

    templates = template_manager.get_templates()
    targets: list[tuple[str, dict[str, Any], str]] = []
    for name, tmpl in templates.items():
        if selected_names and name not in selected_names:
            continue
        url = str(tmpl.get("url") or "")
        if not url.startswith("eufy://"):
            continue
        tmpl_profile, device_id = eufy_cloud.parse_eufy_url(url)
        if tmpl_profile != clean_profile or not device_id:
            continue
        targets.append((name, tmpl, device_id))

    targets.sort(key=lambda row: row[0].lower())
    results: list[dict[str, Any]] = []
    for name, tmpl, device_id in targets:
        try:
            payload, _content_type = eufy_cloud.fetch_snapshot(
                clean_profile,
                device_id,
                timeout=timeout,
            )
            out = _save_snapshot_png(
                name=name,
                payload=payload,
                invert=bool(tmpl.get("invert", False)),
            )
            template_manager.update_last_screenshot_time(name)
            template_manager.clear_offline(name)
            template_manager.set_capture_failed(name, False)
            results.append(
                {
                    "name": name,
                    "profile": clean_profile,
                    "device_id": device_id,
                    "ok": True,
                    "file": out,
                    "error": "",
                }
            )
        except eufy_cloud.EufyCaptchaRequired:
            raise
        except Exception as exc:
            template_manager.set_capture_failed(name, True)
            results.append(
                {
                    "name": name,
                    "profile": clean_profile,
                    "device_id": device_id,
                    "ok": False,
                    "file": "",
                    "error": str(exc),
                }
            )

    return results
