# app/utils/llm.py

import datetime
import json
import logging
import re
import time
from typing import Optional

from app.config import CHATGPT_KEY, LLM_MODEL_VERSION, LLM_SUMMARY_PROMPT
from app.utils import llm_cache

from .api_utils import request_with_retry

last_429_error_time = None


def summarize(
    prompt: str,
    history: Optional[str] = None,
    tokens: int = 4096,
    *,
    timeout: int = 10,
    retries: int = 2,
):
    """
    Generate a summary using OpenAI's GPT model.

    This function sends a request to the OpenAI API to generate a summary based on the given prompt
    and optional history. It handles rate limiting, processes the response, and returns the summary
    as a JSON string.

    Args:
        prompt (str): The main prompt for the summary.
        history (str, optional): Previous context or history to consider. Defaults to None.
        tokens (int, optional): Maximum number of tokens for the response. Defaults to 4096.
        timeout (int, optional): Request timeout in seconds.
        retries (int, optional): Number of retry attempts on failure.

    Returns:
        str: JSON content with the summary or a message if generation fails.
    """
    global last_429_error_time

    # Rate limiting: Check if a 429 error occurred in the last 15 minutes
    if last_429_error_time and (datetime.datetime.now() - last_429_error_time) < datetime.timedelta(minutes=15):
        return None

    if CHATGPT_KEY is None or len(CHATGPT_KEY) < 1 or len(CHATGPT_KEY) > 128:
        return None
    if LLM_SUMMARY_PROMPT is None or len(LLM_SUMMARY_PROMPT) < 1:
        return None

    # Check for cached result
    cache_key = prompt if history is None else f"{prompt}|{history}"
    cached = llm_cache.get(cache_key)
    if cached is not None:
        return cached.get("response")

    # note - if history is None or [], there isnt much to do ..

    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    # Prepare the summary prompt
    lsummary_prompt = LLM_SUMMARY_PROMPT.replace("$datetime", str(datetime.datetime.now()))

    # Construct the messages for the API request
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

    # Prepare the payload for the API request
    model_version = LLM_MODEL_VERSION or "gpt-4.1"  # fallback to gpt-4.1 if unset
    payload = {
        "model": model_version,
        "messages": messages,
        "max_tokens": tokens,
    }

    # Send the request to the OpenAI API
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
            last_429_error_time = datetime.datetime.now()
            logging.warning("429 error encountered. Blocking requests for 15 minutes.")
            return None
        result = response.json()
    except Exception as e:
        logging.warning("API response issue %s", e)
        if cached is not None:
            return cached.get("response")
        return json.dumps({int(time.time()): "Summarization delayed"})

    # Process the API response
    try:
        if (
            result is None
            or not result.get("choices")
            or not result.get("usage")
            or not result["usage"].get("total_tokens")
        ):
            logging.warning("API response missing expected fields: %s", result)
            return None

        response_text = result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
        ltokens = result["usage"]["total_tokens"]
        logging.info("Total tokens used: %s (Cost: $%0.5f)", ltokens, ltokens * 0.005 / 1000)

        # Convert the response text to a JSON format
        ljson = {}
        start_time = int(time.time())
        for line in re.findall(r"(.+?)(?:[\t\n]|$)", response_text, flags=re.DOTALL):
            # Remove asterisks and bullet points
            line = line.replace("**", "").strip()
            line = re.sub(r"^\s?[\*\-]\s?", "", line, flags=re.DOTALL)
            # Remove any single word prefix followed by a colon
            line = re.sub(r"^\w+:\s*", "", line)
            if len(line) > 1:
                ljson[start_time] = line
                start_time += 5

        logging.debug("Processed summary: %s", ljson)
        result_json = json.dumps(ljson)
        llm_cache.store(cache_key, result_json, ltokens)
        return result_json
    except Exception as e:
        logging.exception("GPT response processing exception: %s", e)
        if response is not None:
            logging.debug("GPT response text: %s", response.text)
        return None


def ask_question(question: str, history: str = "", *, timeout: int = 10) -> str | None:
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
        return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:  # pragma: no cover - network errors
        logging.error("ChatGPT request failed: %s", e)
    return None
