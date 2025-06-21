# app/utils/image_processing.py

import base64
import datetime
import io
import logging
import os
import re
from typing import List, Optional

from PIL import Image

from app.config import CHATGPT_KEY, LLM_CAPTION_PROMPT, LLM_MODEL_VERSION
from app.utils import llm_cache
from app.utils.api_utils import SESSION as API_SESSION
from app.utils.api_utils import request_with_retry

HEADER_PREFIX_RE = re.compile(r"^(caption|title|summary):\s*", re.IGNORECASE)


def clean_caption(text: str) -> str:
    """Return caption text without header prefixes or Markdown markers."""

    if not text:
        return ""
    cleaned = text.replace("**", "").strip()
    cleaned = HEADER_PREFIX_RE.sub("", cleaned)
    return cleaned.strip()


last_429_error_time = None


class ChatGPTImageComparison:
    """Helper for caption prompts using the ChatGPT vision API."""

    def __init__(self) -> None:
        self.api_key = CHATGPT_KEY
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.url = "https://api.openai.com/v1/chat/completions"

    def compare_images(
        self, prompt, image_paths, max_size=512, low_res=False, tokens=48
    ):

        global last_429_error_time

        if not self.api_key:
            return None, 0
        # Check if a 429 error occurred in the last 30 minutes
        if last_429_error_time and (
            datetime.datetime.now() - last_429_error_time
        ) < datetime.timedelta(minutes=15):
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

        for image_path in reversed(image_paths):
            if not os.path.exists(image_path):
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
                break

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
                "POST",
                self.url,
                headers=self.headers,
                json=payload,
                timeout=30,
                session=API_SESSION,
            )
            if response.status_code == 429:
                last_429_error_time = datetime.datetime.now()
                logging.warning(
                    "429 error encountered. Blocking requests for 30 minutes."
                )
                return None, 0
            result = response.json()
        except Exception as e:
            logging.warning("API response issue: %s", e)

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
            return None, 0


def chatgpt_compare(
    prompt: str, image_paths: List[str], template_name: Optional[str] = None
) -> Optional[str]:
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
    if len(CHATGPT_KEY) < 1:
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
