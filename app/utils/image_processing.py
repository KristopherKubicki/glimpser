"""Process screenshots and query the ChatGPT vision API.

Functions handle caption prompts, remove borders, detect blank frames and
overlay timestamps.  Responses from the LLM are cached on disk to avoid
repeat charges.  The module supports simplified placeholder generation
when images are missing.
"""

import base64
import datetime
import hashlib
import io
import json
import logging
import os
import re
import tempfile
from contextlib import contextmanager

from PIL import Image, ImageFile

from app import capture_policy
from app.caption_policy import (
    DEFAULT_CAPTION_PROMPT,
    EVIDENCE_GUIDANCE,
    LEGACY_CAPTION_PROMPT,
    main_device_region,
)
from app.capture_policy import caption_image_size
from app.config import (
    CHATGPT_KEY,
    LLM_CAPTION_PROMPT,
    LLM_MODEL_VERSION,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_FALLBACK,
    LOCAL_LLM_VISION_MODEL,
)
from app.utils import llm_cache
from app.utils.api_utils import request_with_retry
from app.utils.caption_context import MARKER, caption_context
from app.utils.local_llm import caption_with_ollama
from app.utils.logging_utils import shared_log_allowed
from app.utils.screenshots import _is_valid_png

# Allow reading truncated images so processing does not fail when a screenshot
# is incomplete.
ImageFile.LOAD_TRUNCATED_IMAGES = True

HEADER_PREFIX_RE = re.compile(r"^(caption|title|summary):\s*", re.IGNORECASE)
TIMESTAMP_FIXATION_RE = re.compile(
    r"\b(timestamp|time\s*stamp|utc|timezone|time\s+zone|clock)\b",
    re.IGNORECASE,
)
TIMESTAMP_ANOMALY_RE = re.compile(
    r"\b(anomal|mismatch|converted|conversion|wrong|incorrect|offset|drift)\b",
    re.IGNORECASE,
)
LLM_OVERLAY_GUIDANCE = (
    "Ignore browser chrome, decorative clocks, barcode markers and prior caption "
    "overlays. Source observation, issue and forecast valid times are evidence: "
    "retain them when legible and relevant to currentness. A fresh screenshot does "
    "not prove fresh source data. Do not diagnose clock offsets from an image."
)
LLM_CACHE_CONTEXT_VERSION = "evidence-context-v5"


def caption_policy_fingerprint() -> str:
    """Identify effective instructions and image policy without the moving clock."""
    policy = {
        "version": LLM_CACHE_CONTEXT_VERSION,
        "prompt": LLM_CAPTION_PROMPT,
        "default_prompt": DEFAULT_CAPTION_PROMPT,
        "evidence": EVIDENCE_GUIDANCE,
        "overlay": LLM_OVERLAY_GUIDANCE,
        "model": LLM_MODEL_VERSION,
        "local_model": LOCAL_LLM_VISION_MODEL,
        "capture_policy": capture_policy.CAPTURE_POLICY,
    }
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def clean_caption(text: str) -> str:
    """Return caption text without header prefixes or Markdown markers."""

    if not text:
        return ""
    cleaned = text.replace("**", "").strip()
    cleaned = HEADER_PREFIX_RE.sub("", cleaned)
    sample = cleaned[:220]
    if TIMESTAMP_FIXATION_RE.search(sample) and TIMESTAMP_ANOMALY_RE.search(sample):
        logging.info("Discarding timestamp-fixated LLM caption: %s", sample)
        return "UNREADABLE"
    return cleaned.strip()


def _caption_system_prompt() -> str:
    """Return the system prompt with current time and overlay guidance."""

    prompt = LLM_CAPTION_PROMPT
    if prompt == LEGACY_CAPTION_PROMPT:
        prompt = DEFAULT_CAPTION_PROMPT
    prompt = prompt.replace("$datetime", str(datetime.datetime.utcnow()))
    return f"{prompt.rstrip()}\n\n{LLM_OVERLAY_GUIDANCE}\n{EVIDENCE_GUIDANCE}"


def _caption_cache_prompt(prompt: str) -> str:
    """Return a stable cache key component for caption prompt behavior."""

    return (
        f"{prompt}\n\n[caption-cache:{LLM_CACHE_CONTEXT_VERSION}]"
        f"\n[caption-policy:{caption_policy_fingerprint()}]"
    )


def _caption_user_prompt(prompt: str, template_name: str | None = None) -> str:
    """Return template-specific user guidance for scene captions."""

    effective_prompt = str(prompt or "")
    if str(template_name or "").strip().lower().startswith("hubitat"):
        effective_prompt = (
            f"{effective_prompt.rstrip()}\n\n"
            "For this Hubitat dashboard, use visible card names to attribute up to "
            "three readable device/security/mode states or errors. Omit the full "
            "tile inventory. Ignore decorative card styling, blue accent bars, "
            "barcode markers, and capture overlays."
        )
    return effective_prompt


RATE_LIMIT_BACKOFF_MINUTES = 15
LLM_429_WINDOW_SECONDS = int(os.getenv("LLM_429_WINDOW_SECONDS", "600"))
LLM_429_HARD_LIMIT = int(os.getenv("LLM_429_HARD_LIMIT", "6"))
LLM_429_HARD_BACKOFF_MINUTES = int(os.getenv("LLM_429_HARD_BACKOFF_MINUTES", "60"))
LLM_429_LOG_INTERVAL_SECONDS = int(os.getenv("LLM_429_LOG_INTERVAL_SECONDS", "300"))
last_429_error_time = None
last_429_log_time = None
_backoff_until = None
_recent_429s: list[float] = []
_last_429_warn_time: float | None = None


def _log_backoff(reason: str, model: str, remaining_seconds: float) -> None:
    global last_429_log_time
    now = datetime.datetime.now()
    if last_429_log_time and (now - last_429_log_time).total_seconds() < 300:
        return
    last_429_log_time = now
    logging.warning(
        "LLM backoff active (%s); skipping captions for %ds. model=%s",
        reason,
        int(remaining_seconds),
        model,
    )


def _record_429(now: datetime.datetime) -> int:
    global _recent_429s
    cutoff = now.timestamp() - LLM_429_WINDOW_SECONDS
    _recent_429s = [ts for ts in _recent_429s if ts >= cutoff]
    _recent_429s.append(now.timestamp())
    return len(_recent_429s)


def _should_warn_429(now: datetime.datetime) -> bool:
    global _last_429_warn_time
    if _last_429_warn_time and (now - _last_429_warn_time).total_seconds() < 300:
        return False
    _last_429_warn_time = now
    return True


def _local_caption_fallback(
    prompt: str, image_paths: list[str], llm_prompt: str
) -> tuple[str | None, int]:
    """Best-effort local caption fallback using Ollama-compatible API."""

    if not LOCAL_LLM_FALLBACK:
        return None, 0
    result = caption_with_ollama(
        model=LOCAL_LLM_VISION_MODEL,
        system_prompt=llm_prompt,
        prompt=prompt,
        image_paths=image_paths,
    )
    if result:
        logging.info(
            "Local LLM fallback produced caption via %s (%s)",
            LOCAL_LLM_VISION_MODEL,
            LOCAL_LLM_BASE_URL,
        )
        return clean_caption(result), 0
    return None, 0


def _is_unsupported_max_tokens_error(result: object) -> bool:
    """Return True when the API rejects max_tokens for this model."""

    if not isinstance(result, dict):
        return False
    err = result.get("error")
    if not isinstance(err, dict):
        return False

    param = str(err.get("param", "")).strip().lower()
    message = str(err.get("message", "")).strip().lower()
    code = str(err.get("code", "")).strip().lower()

    if param == "max_tokens":
        return True
    if code == "unsupported_parameter" and "max_tokens" in message:
        return True
    return "unsupported parameter" in message and "max_tokens" in message


def _uses_completion_token_param(model: str) -> bool:
    """Return True for models that use max_completion_tokens."""

    normalized = str(model or "").strip().lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4"))


def _completion_token_budget(tokens: int) -> int:
    """Return a safe max_completion_tokens budget for terse captions."""

    try:
        requested = int(tokens)
    except Exception:
        requested = 48
    # GPT-5 style models count hidden reasoning against max_completion_tokens,
    # so a classic 48-token caption cap can yield an empty visible response.
    return max(1024, requested * 8)


def _reasoning_effort_for_model(model: str) -> str | None:
    """Return low-latency reasoning effort for caption-sized vision calls."""

    normalized = str(model or "").strip().lower()
    if normalized.startswith("gpt-5.1"):
        return "none"
    if normalized.startswith("gpt-5"):
        return "minimal"
    if normalized.startswith(("o1", "o3", "o4")):
        return "low"
    return None


def _chat_completion_token_payload(model: str, tokens: int) -> dict[str, int | str]:
    """Return generation controls supported by the selected chat model."""

    if _uses_completion_token_param(model):
        payload: dict[str, int | str] = {
            "max_completion_tokens": _completion_token_budget(tokens)
        }
        reasoning_effort = _reasoning_effort_for_model(model)
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        return payload
    return {"max_tokens": tokens}


def _request_chat_completion(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: int,
):
    """Issue a chat-completions request with token-parameter compatibility."""

    response = request_with_retry(
        "POST", url, headers=headers, json=payload, timeout=timeout
    )
    try:
        result = response.json()
    except Exception:
        result = None

    if _is_unsupported_max_tokens_error(result) and "max_tokens" in payload:
        compat_payload = dict(payload)
        token_budget = int(compat_payload.pop("max_tokens", 0) or 0)
        compat_payload["max_completion_tokens"] = _completion_token_budget(token_budget)
        reasoning_effort = _reasoning_effort_for_model(str(compat_payload.get("model")))
        if reasoning_effort:
            compat_payload["reasoning_effort"] = reasoning_effort
        logging.info(
            "Retrying vision completion with max_completion_tokens. model=%s",
            compat_payload.get("model"),
        )
        response = request_with_retry(
            "POST", url, headers=headers, json=compat_payload, timeout=timeout
        )
        try:
            result = response.json()
        except Exception:
            result = None

    return response, result


def _extract_chat_message_text(result: object) -> str:
    """Extract text content from chat-completions response shapes."""

    if not isinstance(result, dict):
        return ""
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    return ""


class ChatGPTImageComparison:
    """Helper for caption prompts using the ChatGPT vision API."""

    def __init__(self) -> None:
        self.api_key = CHATGPT_KEY
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.url = "https://api.openai.com/v1/chat/completions"

    def compare_images(
        self,
        prompt: str,
        image_paths: list[str],
        max_size: int = 512,
        low_res: bool = False,
        tokens: int = 48,
    ) -> tuple[str | None, int]:
        """Return a caption for ``image_paths`` using the ChatGPT vision API.

        Parameters
        ----------
        prompt : str
            The text prompt describing the images.
        image_paths : List[str]
            Paths to images to send to ChatGPT; the newest valid image will be
            used.
        max_size : int, optional
            Maximum dimension of the resized image. Defaults to ``512``.
        low_res : bool, optional
            Request lower detail when ``True``. Defaults to ``False``.
        tokens : int, optional
            Maximum tokens to request from the API. Defaults to ``48``.

        Returns
        -------
        tuple[str | None, int]
            The cleaned caption text (``None`` on error) and the number of
            tokens consumed.
        """

        global last_429_error_time, _backoff_until

        if not self.api_key:
            llm_prompt = _caption_system_prompt()
            return _local_caption_fallback(prompt, image_paths, llm_prompt)
        # Check if a 429 error occurred in the last window.
        now = datetime.datetime.now()
        if _backoff_until and now < _backoff_until:
            remaining = (_backoff_until - now).total_seconds()
            _log_backoff("rate_limited", LLM_MODEL_VERSION, remaining)
            llm_prompt = _caption_system_prompt()
            local = _local_caption_fallback(prompt, image_paths, llm_prompt)
            if local[0]:
                return local
            return None, 0

        detail = "high"
        if low_res is True:
            detail = "low"

        llm_prompt = _caption_system_prompt()

        # Load, downsample while preserving aspect ratio, and convert images to base64
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": llm_prompt}],
            }
        ]
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})

        valid_image_added = False
        for image_path in reversed(image_paths):
            if not os.path.exists(image_path):
                continue
            if not _is_valid_png(image_path):
                logging.warning("Invalid image for ChatGPT comparison: %s", image_path)
                continue
            with Image.open(image_path).convert("RGB") as img:
                # Calculate new size preserving aspect ratio
                ratio = min(max_size / img.size[0], max_size / img.size[1])
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                # Resize and convert to base64
                img_resized = img.resize(new_size)
                buffer = io.BytesIO()
                img_resized.save(buffer, format="JPEG")
                base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": f"{detail}",
                                },
                            }
                        ],
                    }
                )
                valid_image_added = True
                break

        if not valid_image_added:
            logging.warning("No valid images found for ChatGPT comparison")
            return None, 0

        # Construct the payload with the prompt and images
        payload = {
            "model": LLM_MODEL_VERSION,
            "messages": messages,
        }
        payload.update(_chat_completion_token_payload(LLM_MODEL_VERSION, tokens))

        # Send the request to the API with retry logic
        result = None
        try:
            response, result = _request_chat_completion(
                url=self.url,
                headers=self.headers,
                payload=payload,
                timeout=30,
            )
            if response.status_code == 429:
                last_429_error_time = now
                count = _record_429(now)
                retry_after = response.headers.get("Retry-After")
                extra = f" retry_after={retry_after}" if retry_after else ""
                backoff_minutes = RATE_LIMIT_BACKOFF_MINUTES
                if count >= LLM_429_HARD_LIMIT:
                    backoff_minutes = max(backoff_minutes, LLM_429_HARD_BACKOFF_MINUTES)
                _backoff_until = now + datetime.timedelta(minutes=backoff_minutes)
                if _should_warn_429(now) and shared_log_allowed(
                    "llm_429_caption", LLM_429_LOG_INTERVAL_SECONDS
                ):
                    logging.warning(
                        "LLM rate limit (HTTP 429) from OpenAI; pausing captions for %d minutes (count=%d/%d). model=%s.%s",
                        backoff_minutes,
                        count,
                        LLM_429_HARD_LIMIT,
                        LLM_MODEL_VERSION,
                        extra,
                    )
                local = _local_caption_fallback(prompt, image_paths, llm_prompt)
                if local[0]:
                    return local
                return None, 0
        except Exception as e:
            logging.warning("API response issue: %s", e)
            local = _local_caption_fallback(prompt, image_paths, llm_prompt)
            if local[0]:
                return local

        # Process the response
        # For demonstration, we'll just return the text response
        try:
            raw_text = _extract_chat_message_text(result).replace("\n\n", "\t").strip()
            response_text = clean_caption(raw_text)
            ltokens = int(result.get("usage", {}).get("total_tokens", 0))
            if not response_text:
                choice = (result.get("choices") or [{}])[0] if result else {}
                logging.warning(
                    "Empty LLM caption response. finish_reason=%s usage=%s model=%s",
                    choice.get("finish_reason") if isinstance(choice, dict) else None,
                    result.get("usage") if isinstance(result, dict) else None,
                    LLM_MODEL_VERSION,
                )
                local = _local_caption_fallback(prompt, image_paths, llm_prompt)
                if local[0]:
                    return local
                return None, ltokens
            logging.info(
                " total tokens $%0.5f images: %d %s",
                ltokens * 0.005 / 1000,
                len(image_paths),
                image_paths[-1],
            )
            return response_text, ltokens
        except Exception:
            local = _local_caption_fallback(prompt, image_paths, llm_prompt)
            if local[0]:
                return local
            return None, 0


@contextmanager
def _caption_analysis_paths(template_name, image_paths):
    """Hide embedded camera captions from the known Main dashboard layout.

    The full capture remains untouched. Both cloud and local captioners receive
    the device-card region; unexpected dimensions fail closed until reviewed.
    """
    if template_name != "HubitatMain":
        yield image_paths
        return
    with tempfile.TemporaryDirectory(prefix="glimpser-caption-") as directory:
        paths = []
        for index, path in enumerate(image_paths):
            try:
                with Image.open(path) as image:
                    region = main_device_region(image)
                    if region is None:
                        logging.warning(
                            "HubitatMain caption layout needs review: %s", image.size
                        )
                        yield []
                        return
                    target = os.path.join(directory, f"device-cards-{index}.png")
                    image.crop(region).save(target)
                    paths.append(target)
            except (OSError, ValueError):
                yield []
                return
        yield paths


def chatgpt_compare(
    prompt: str, image_paths: list[str], template_name: str | None = None
) -> str | None:
    """Return a caption for images via ChatGPT.

    Cached responses are reused and token usage is recorded when
    ``template_name`` is provided. Returns ``None`` on API failure or a
    descriptive message when inputs are invalid.
    """

    # Both cloud and fallback describe the requested current observation only.
    image_paths = image_paths[-1:]
    if not image_paths:
        return None

    # Check if all images exist
    for image in image_paths:
        if not os.path.exists(image):
            return None

    # Use the ChatGPT API for comparison
    if len(CHATGPT_KEY) < 1 and not LOCAL_LLM_FALLBACK:
        return None

    if MARKER not in prompt:
        prompt += caption_context(template_name, image_paths)
    effective_prompt = _caption_user_prompt(prompt, template_name)
    cache_prompt = _caption_cache_prompt(effective_prompt)
    cached = llm_cache.get(cache_prompt, image_paths)
    if cached is not None:
        result = clean_caption(cached.get("response"))
        tokens = cached.get("tokens", 0)
    else:
        chatgpt_comparison = ChatGPTImageComparison()
        # Preserve enough pixels to read device values and distinguish reflections.
        max_size = caption_image_size(template_name)
        with _caption_analysis_paths(template_name, image_paths) as analysis_paths:
            if not analysis_paths:
                return None
            result, tokens = chatgpt_comparison.compare_images(
                effective_prompt, analysis_paths, max_size=max_size
            )
        if result:
            llm_cache.store(cache_prompt, result, tokens, image_paths)
            result = clean_caption(result)

    if template_name and tokens:
        try:
            from app.utils.template_manager import record_llm_usage

            record_llm_usage(template_name, tokens)
        except Exception as e:
            logging.error("Failed to record token usage: %s", e)

    return result
