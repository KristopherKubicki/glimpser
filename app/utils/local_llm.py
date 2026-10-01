"""Helpers for local LLM/Ollama fallbacks.

These functions are intentionally lightweight wrappers that can be used when
remote providers are rate-limited or unavailable.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import Any

from PIL import Image

from app.utils.api_utils import request_with_retry
from app.utils.screenshots import _is_valid_png

LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
LOCAL_LLM_TIMEOUT_SECONDS = int(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "90"))


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _post_ollama(
    payload: dict[str, Any], timeout: int | None = None
) -> dict[str, Any] | None:
    url = _join_url(LOCAL_LLM_BASE_URL, "/api/chat")
    effective_timeout = timeout or LOCAL_LLM_TIMEOUT_SECONDS
    try:
        resp = request_with_retry(
            "post",
            url,
            json=payload,
            timeout=effective_timeout,
            retries=0,
        )
        if not getattr(resp, "ok", False):
            logging.warning(
                "Local LLM request failed: status=%s model=%s",
                getattr(resp, "status_code", "?"),
                payload.get("model"),
            )
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        return data
    except Exception as exc:
        logging.warning("Local LLM request error: %s", exc)
        return None


def _extract_message_text(data: dict[str, Any]) -> str | None:
    message = data.get("message")
    if isinstance(message, dict):
        text = message.get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()
    text = data.get("response")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _image_to_base64_jpeg(image_path: str, max_size: int = 512) -> str | None:
    if not os.path.exists(image_path):
        return None
    if not _is_valid_png(image_path):
        return None
    try:
        with Image.open(image_path).convert("RGB") as img:
            ratio = min(max_size / img.size[0], max_size / img.size[1])
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img_resized = img.resize(new_size)
            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as exc:
        logging.warning("Local LLM image conversion failed for %s: %s", image_path, exc)
        return None


def _image_bytes_to_base64_jpeg(image_bytes: bytes, max_size: int = 512) -> str | None:
    if not image_bytes:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            ratio = min(max_size / img.size[0], max_size / img.size[1])
            new_size = (
                max(1, int(img.size[0] * ratio)),
                max(1, int(img.size[1] * ratio)),
            )
            img_resized = img.resize(new_size)
            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as exc:
        logging.warning("Local LLM image conversion failed: %s", exc)
        return None


def caption_with_ollama(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    image_paths: list[str],
    max_size: int = 512,
) -> str | None:
    """Return a vision caption from a local Ollama model."""

    base64_image = None
    for path in reversed(image_paths):
        base64_image = _image_to_base64_jpeg(path, max_size=max_size)
        if base64_image:
            break
    if not base64_image:
        return None

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
                "images": [base64_image],
            },
        ],
    }
    data = _post_ollama(payload)
    if not data:
        return None
    return _extract_message_text(data)


def ocr_with_ollama(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    image_bytes: bytes,
    max_size: int = 512,
    timeout: int | None = None,
    options: dict[str, Any] | None = None,
) -> str | None:
    """Return OCR text from a local Ollama vision-capable model."""

    base64_image = _image_bytes_to_base64_jpeg(image_bytes, max_size=max_size)
    if not base64_image:
        return None

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
                "images": [base64_image],
            },
        ],
    }
    if options:
        payload["options"] = options
    data = _post_ollama(payload, timeout=timeout)
    if not data:
        return None
    return _extract_message_text(data)


def summarize_with_ollama(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    history: str | None = None,
) -> str | None:
    """Return a summary string from a local Ollama text model."""

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": prompt})
    if history:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Also, please note the previous transcripts. "
                    "Try to build on the history if you can, without repeating "
                    "the older content.\n: " + history
                ),
            }
        )

    payload = {"model": model, "stream": False, "messages": messages}
    data = _post_ollama(payload)
    if not data:
        return None
    return _extract_message_text(data)
