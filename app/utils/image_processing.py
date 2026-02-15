"""Process screenshots and query the ChatGPT vision API.

Functions handle caption prompts, remove borders, detect blank frames and
overlay timestamps.  Responses from the LLM are cached on disk to avoid
repeat charges.  The module supports simplified placeholder generation
when images are missing.
"""

import base64
import datetime
import io
import logging
import os
import re

from PIL import Image, ImageFile

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
from app.utils.local_llm import caption_with_ollama
from app.utils.logging_utils import shared_log_allowed
from app.utils.screenshots import _is_valid_png

# Allow reading truncated images so processing does not fail when a screenshot
# is incomplete.
ImageFile.LOAD_TRUNCATED_IMAGES = True

HEADER_PREFIX_RE = re.compile(r"^(caption|title|summary):\s*", re.IGNORECASE)


def clean_caption(text: str) -> str:
    """Return caption text without header prefixes or Markdown markers."""

    if not text:
        return ""
    cleaned = text.replace("**", "").strip()
    cleaned = HEADER_PREFIX_RE.sub("", cleaned)
    return cleaned.strip()


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
            Paths to images to send to ChatGPT; the first existing image will be
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
            llm_prompt = LLM_CAPTION_PROMPT.replace(
                "$datetime", str(datetime.datetime.utcnow())
            )
            return _local_caption_fallback(prompt, image_paths, llm_prompt)
        # Check if a 429 error occurred in the last window.
        now = datetime.datetime.now()
        if _backoff_until and now < _backoff_until:
            remaining = (_backoff_until - now).total_seconds()
            _log_backoff("rate_limited", LLM_MODEL_VERSION, remaining)
            llm_prompt = LLM_CAPTION_PROMPT.replace(
                "$datetime", str(datetime.datetime.utcnow())
            )
            local = _local_caption_fallback(prompt, image_paths, llm_prompt)
            if local[0]:
                return local
            return None, 0

        detail = "high"
        if low_res is True:
            detail = "low"

        llm_prompt = LLM_CAPTION_PROMPT
        llm_prompt = llm_prompt.replace("$datetime", str(datetime.datetime.utcnow()))

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
            "max_tokens": tokens,  # might even be less
        }

        # Send the request to the API with retry logic
        result = None
        try:
            response = request_with_retry(
                "POST", self.url, headers=self.headers, json=payload, timeout=30
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
            result = response.json()
        except Exception as e:
            logging.warning("API response issue: %s", e)
            local = _local_caption_fallback(prompt, image_paths, llm_prompt)
            if local[0]:
                return local

        # Process the response
        # For demonstration, we'll just return the text response
        try:
            raw_text = (
                result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
            )
            response_text = clean_caption(raw_text)
            ltokens = result["usage"]["total_tokens"]
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


def chatgpt_compare(
    prompt: str, image_paths: list[str], template_name: str | None = None
) -> str | None:
    """Return a caption for images via ChatGPT.

    Cached responses are reused and token usage is recorded when
    ``template_name`` is provided. Returns ``None`` on API failure or a
    descriptive message when inputs are invalid.
    """

    # Check if all images exist
    for image in image_paths:
        if not os.path.exists(image):
            return "Missing image"

    # Use the ChatGPT API for comparison
    if len(CHATGPT_KEY) < 1 and not LOCAL_LLM_FALLBACK:
        return "Missing ChatGPT key"

    cached = llm_cache.get(prompt, image_paths)
    if cached is not None:
        result = clean_caption(cached.get("response"))
        tokens = cached.get("tokens", 0)
    else:
        chatgpt_comparison = ChatGPTImageComparison()
        result, tokens = chatgpt_comparison.compare_images(prompt, image_paths)
        if result:
            llm_cache.store(prompt, result, tokens, image_paths)
            result = clean_caption(result)

    if template_name and tokens:
        try:
            from app.utils.template_manager import record_llm_usage

            record_llm_usage(template_name, tokens)
        except Exception as e:
            logging.error("Failed to record token usage: %s", e)

    return result
