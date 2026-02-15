"""Interact with LLM providers to generate text summaries.

Primary provider is OpenAI. Optional local fallback (for example Ollama) can
be enabled to keep summaries flowing during 429s/outages.
"""

import datetime
import json
import logging
import os
import re
import time

from app.config import (
    CHATGPT_KEY,
    LLM_MODEL_VERSION,
    LLM_SUMMARY_PROMPT,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_FALLBACK,
    LOCAL_LLM_TEXT_MODEL,
)
from app.utils import llm_cache
from app.utils.logging_utils import shared_log_allowed

from .api_utils import request_with_retry
from .local_llm import summarize_with_ollama

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
        "LLM backoff active (%s); skipping summaries for %ds. model=%s",
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


def _response_text_to_json(response_text: str) -> str:
    """Normalize summary text into the persisted JSON line format."""

    ljson = {}
    start_time = int(time.time() + 0.5)
    for line in re.findall(r"(.+?)(?:[\t\n]|$)", response_text, flags=re.DOTALL):
        line = line.replace("**", "").strip()
        line = re.sub(r"^\s?[\*\-]\s?", "", line, flags=re.DOTALL)
        line = re.sub(r"^\w+:\s*", "", line)
        if len(line) > 1:
            ljson[start_time] = line
            start_time += 5
    return json.dumps(ljson)


def _local_summary_fallback(
    prompt: str, history: str | None, summary_prompt: str
) -> str | None:
    """Best-effort local summary fallback using Ollama-compatible API."""

    if not LOCAL_LLM_FALLBACK:
        return None
    text = summarize_with_ollama(
        model=LOCAL_LLM_TEXT_MODEL,
        system_prompt=summary_prompt,
        prompt=prompt,
        history=history,
    )
    if not text:
        return None
    logging.info(
        "Local LLM fallback produced summary via %s (%s)",
        LOCAL_LLM_TEXT_MODEL,
        LOCAL_LLM_BASE_URL,
    )
    return _response_text_to_json(text)


def summarize(
    prompt: str,
    history: str | None = None,
    tokens: int = 4096,
    *,
    timeout: int = 30,
    retries: int = 2,
):
    """Generate a summary. Uses OpenAI first, local fallback optionally."""

    global last_429_error_time, _backoff_until

    # Check cache first regardless of provider.
    cache_key = prompt if history is None else f"{prompt}|{history}"
    cached = llm_cache.get(cache_key)
    if cached is not None:
        return cached.get("response")

    # Prepare the summary prompt once for whichever provider answers.
    lsummary_prompt = LLM_SUMMARY_PROMPT.replace(
        "$datetime", str(datetime.datetime.now())
    )

    now = datetime.datetime.now()
    if _backoff_until and now < _backoff_until:
        remaining = (_backoff_until - now).total_seconds()
        _log_backoff("rate_limited", LLM_MODEL_VERSION or "gpt-4.1", remaining)
        local = _local_summary_fallback(prompt, history, lsummary_prompt)
        if local:
            llm_cache.store(cache_key, local, 0)
            return local
        return None

    if last_429_error_time:
        elapsed = (now - last_429_error_time).total_seconds()
        if elapsed < RATE_LIMIT_BACKOFF_MINUTES * 60:
            remaining = RATE_LIMIT_BACKOFF_MINUTES * 60 - elapsed
            _log_backoff("recent_429", LLM_MODEL_VERSION or "gpt-4.1", remaining)
            local = _local_summary_fallback(prompt, history, lsummary_prompt)
            if local:
                llm_cache.store(cache_key, local, 0)
                return local
            return None

    if CHATGPT_KEY is None or len(CHATGPT_KEY) < 1 or len(CHATGPT_KEY) > 128:
        local = _local_summary_fallback(prompt, history, lsummary_prompt)
        if local:
            llm_cache.store(cache_key, local, 0)
            return local
        return None
    if LLM_SUMMARY_PROMPT is None or len(LLM_SUMMARY_PROMPT) < 1:
        return None

    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    messages = [
        {"role": "system", "content": [{"type": "text", "text": lsummary_prompt}]},
        {"role": "user", "content": [{"type": "text", "text": prompt}]},
    ]
    if history:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Also, please note the previous transcripts. Try to build on the history if you can, without repeating the older content. \n: "
                        + history,
                    }
                ],
            }
        )

    model_version = LLM_MODEL_VERSION or "gpt-4.1"
    payload = {
        "model": model_version,
        "messages": messages,
        "max_tokens": tokens,
    }

    try:
        response = request_with_retry(
            "post",
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
            retries=retries,
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
                "llm_429_summary", LLM_429_LOG_INTERVAL_SECONDS
            ):
                logging.warning(
                    "LLM rate limit (HTTP 429) from OpenAI; pausing summaries for %d minutes (count=%d/%d). model=%s.%s",
                    backoff_minutes,
                    count,
                    LLM_429_HARD_LIMIT,
                    model_version,
                    extra,
                )
            local = _local_summary_fallback(prompt, history, lsummary_prompt)
            if local:
                llm_cache.store(cache_key, local, 0)
                return local
            return None
        result = response.json()
    except Exception as e:
        logging.warning("API response issue %s", e)
        local = _local_summary_fallback(prompt, history, lsummary_prompt)
        if local:
            llm_cache.store(cache_key, local, 0)
            return local
        return json.dumps({int(time.time()): "Summarization delayed"})

    try:
        if (
            result is None
            or not result.get("choices")
            or not result.get("usage")
            or not result["usage"].get("total_tokens")
        ):
            logging.warning("API response missing expected fields: %s", result)
            local = _local_summary_fallback(prompt, history, lsummary_prompt)
            if local:
                llm_cache.store(cache_key, local, 0)
                return local
            return None

        response_text = (
            result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
        )
        ltokens = result["usage"]["total_tokens"]
        logging.info(
            "Total tokens used: %s (Cost: $%0.5f)", ltokens, ltokens * 0.005 / 1000
        )

        result_json = _response_text_to_json(response_text)
        llm_cache.store(cache_key, result_json, ltokens)
        return result_json
    except Exception as e:
        logging.exception("GPT response processing exception: %s", e)
        if response is not None:
            logging.debug("GPT response text: %s", response.text)
        local = _local_summary_fallback(prompt, history, lsummary_prompt)
        if local:
            llm_cache.store(cache_key, local, 0)
            return local
        return None


def ask_question(question: str, history: str = "", *, timeout: int = 30) -> str | None:
    """Return the answer to ``question`` using ``history`` as context."""

    if not question or not CHATGPT_KEY:
        return None

    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    messages = [
        {
            "role": "system",
            "content": "Answer the user's question using the provided caption history.",
        },
    ]
    if history:
        messages.append({"role": "user", "content": history})
    messages.append({"role": "user", "content": question})

    payload = {
        "model": LLM_MODEL_VERSION or "gpt-4.1",
        "messages": messages,
        "max_tokens": 512,
    }

    try:
        response = request_with_retry(
            "post",
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        result = response.json()
        return (
            result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        )
    except Exception as e:  # pragma: no cover - network errors
        logging.error("ChatGPT request failed: %s", e)
    return None
