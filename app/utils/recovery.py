"""Camera recovery helpers using web search suggestions and previews."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app import config
from app.utils import validators
from app.utils.http_probe import probe_url_with_range
from app.utils.screenshots import (
    CAPTURE_TIMEOUT,
    FFMPEG_HWACCEL,
    FFMPEG_PATH,
    capture_frame_from_stream,
    capture_frame_with_ytdlp,
    capture_screenshot_and_har_light,
    download_image,
    is_image_url,
    is_pdf_url,
    is_video_stream_url,
    sanitize_url,
)

RECOVERY_DIR = Path("data/screenshots/_recovery")
RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
RECOVERY_PREVIEW_TTL = timedelta(hours=6)


def _cleanup_previews() -> None:
    cutoff = datetime.now() - RECOVERY_PREVIEW_TTL
    for path in RECOVERY_DIR.glob("recovery_*.png"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _extract_json_block(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def search_alternatives(
    template: dict[str, Any],
    description: str,
    exclude_urls: list[str] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Return alternative public camera URLs using OpenAI web search."""

    api_key = config.CHATGPT_KEY
    if not api_key:
        raise RuntimeError("OpenAI API key is not configured")

    exclude_urls = exclude_urls or []
    name = template.get("name") or ""
    current_url = template.get("url") or ""
    groups = template.get("groups") or ""
    notes = template.get("notes") or ""

    base_desc = description.strip()
    if not base_desc:
        base_desc = f"{name}. {notes}".strip()

    prompt_lines = [
        "Find alternative public camera feed URLs for the following camera.",
        "Return only public, directly accessible URLs.",
        "Prefer live camera feeds (snapshot JPEG/PNG, public MJPEG, public RTSP, or public YouTube live).",
        "",
        "Respond with JSON only in this schema:",
        "{",
        '  "candidates": [',
        '    {"title": "...", "url": "...", "source": "...", "notes": "..."}',
        "  ]",
        "}",
        "",
        f"Camera name: {name}",
        f"Description: {base_desc}",
        f"Groups: {groups}",
        f"Notes: {notes}",
        f"Current URL: {current_url}",
    ]
    prompt = "\n".join(prompt_lines)
    if exclude_urls:
        prompt += "Avoid these URLs:\n" + "\n".join(exclude_urls)

    payload = {
        "model": config.RECOVERY_SEARCH_MODEL,
        "tools": [{"type": "web_search"}],
        "input": prompt,
        "temperature": 0.2,
        "include": ["web_search_call.action.sources"],
    }

    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    output_text = ""
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") in {"output_text", "text"}:
                output_text += part.get("text", "")

    parsed = _extract_json_block(output_text)
    if not parsed:
        raise RuntimeError("No JSON candidates returned")

    candidates = parsed.get("candidates", [])
    cleaned: list[dict[str, str]] = []
    for cand in candidates:
        url = (cand.get("url") or "").strip()
        if not validators.is_public_url(url):
            continue
        cleaned.append(
            {
                "title": str(cand.get("title") or "")[:200],
                "url": url,
                "source": str(cand.get("source") or "")[:200],
                "notes": str(cand.get("notes") or "")[:400],
            }
        )

    return cleaned, prompt


def generate_preview(
    url: str, template_name: str
) -> tuple[str | None, str | None, str | None]:
    """Generate a preview image for the URL and return the file path."""

    _cleanup_previews()

    url = validate_recovery_url(url)
    if not url:
        return None, None, "Invalid or non-public URL"

    token = uuid.uuid4().hex
    base_path = RECOVERY_DIR / f"recovery_{token}"
    image_path = base_path.with_suffix(".png")
    video_path = base_path.with_suffix(".mp4")

    success = False
    error = None
    clean_url = sanitize_url(url)
    timeout = min(int(CAPTURE_TIMEOUT), 15)
    preview_kind = "image"

    try:
        if "youtube.com" in url or "youtu.be" in url:
            success = _capture_preview_clip(url, str(video_path), timeout) or False
            if success:
                preview_kind = "video"
            else:
                success = capture_frame_with_ytdlp(url, str(image_path), template_name)
        else:
            ok, info = _probe_url_kind(url)
            kind = info.get("kind") if ok else None
            if kind == "image" or is_image_url(url, info.get("content_type", "")):
                success = download_image(
                    url,
                    str(image_path),
                    timeout,
                    template_name,
                    invert=False,
                    dark=True,
                    stealth=False,
                    proxy=None,
                    username=None,
                    password=None,
                )
            elif kind == "video" or is_video_stream_url(
                url, info.get("content_type", "")
            ):
                success = _capture_preview_clip(url, str(video_path), timeout)
                if success:
                    preview_kind = "video"
                else:
                    success = capture_frame_from_stream(
                        url, str(image_path), timeout, template_name
                    )
            elif kind == "pdf" or is_pdf_url(url, info.get("content_type", "")):
                success = capture_screenshot_and_har_light(
                    url, str(image_path), timeout, template_name
                )
            else:
                success = capture_screenshot_and_har_light(
                    url, str(image_path), timeout, template_name
                )
    except Exception as exc:  # pragma: no cover - unexpected runtime
        logging.warning("Recovery preview failed for %s: %s", clean_url, exc)
        error = "Preview failed"

    if not success:
        return None, None, error or "Preview failed"
    path = str(video_path if preview_kind == "video" else image_path)
    return path, preview_kind, None


def _probe_url_kind(url: str) -> tuple[bool, dict[str, Any]]:
    """Lightweight probe to identify content type for recovery previews."""

    ok, info = probe_url_with_range(url, timeout=3, preconnect=True)
    if not ok:
        return False, {}

    status = int(info.get("status", 0) or 0)
    content_type = str(info.get("content_type", ""))

    kind = "webpage"
    if is_image_url(url, content_type):
        kind = "image"
    elif is_pdf_url(url, content_type):
        kind = "pdf"
    elif is_video_stream_url(url, content_type):
        kind = "video"

    return True, {"status": status, "content_type": content_type, "kind": kind}


def validate_recovery_url(url: str) -> str | None:
    """Validate URLs for recovery (http/https/rtsp, public only)."""

    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https", "rtsp"}:
        return None
    if not parsed.netloc:
        return None
    if not validators.is_public_url(url):
        return None
    return url


def _capture_preview_clip(url: str, output_path: str, timeout: int) -> bool:
    """Capture a short preview clip with ffmpeg."""

    try:
        cmd = [FFMPEG_PATH, "-hide_banner", "-loglevel", "error"]
        if FFMPEG_HWACCEL and str(FFMPEG_HWACCEL).lower() != "false":
            cmd.extend(["-hwaccel", FFMPEG_HWACCEL])
        cmd.extend(
            [
                "-t",
                "5",
                "-i",
                url,
                "-an",
                "-sn",
                "-movflags",
                "+faststart",
                "-vf",
                "scale=1280:-2",
                "-preset",
                "veryfast",
                "-y",
                output_path,
            ]
        )
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return proc.returncode == 0 and Path(output_path).exists()
    except Exception:
        return False
