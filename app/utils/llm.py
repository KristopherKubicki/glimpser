import datetime
import json
import re
import time

import requests

from app.config import CHATGPT_KEY, LLM_MODEL_VERSION, LLM_SUMMARY_PROMPT

last_429_error_time = None


def summarize(prompt, history=None, tokens=4096):
    """
    Generate a summary using OpenAI's GPT model.

    This function sends a request to the OpenAI API to generate a summary based on
    the given prompt and optional history. It handles rate limiting, processes the
    response, and formats the output as a JSON string.

    Args:
        prompt (str): The main prompt for the summary.
        history (str, optional): Previous context or history to consider.
        tokens (int, optional): Maximum number of tokens for the response. Defaults to 4096.

    Returns:
        str: A JSON string containing the summarized content, or None if an error occurs.
    """
    global last_429_error_time

    # Check if a 429 error (rate limit) occurred in the last 15 minutes
    if last_429_error_time and (
        datetime.datetime.now() - last_429_error_time
    ) < datetime.timedelta(minutes=15):
        return None

    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    # Prepare the summary prompt
    lsummary_prompt = LLM_SUMMARY_PROMPT.replace("$datetime", str(datetime.datetime.now()))

    # Construct the messages for the API request
    messages = [
        {"role": "system", "content": [{"type": "text", "text": lsummary_prompt}]}
    ]
    messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
    if history:
        messages.append({
            "role": "user",
            "content": [{
                "type": "text",
                "text": "Also, please note the previous transcripts. Try to build on the history if you can, without repeating the older content. \n: " + history,
            }],
        })

    # Construct the payload for the API request
    payload = {
        "model": LLM_MODEL_VERSION,
        "messages": messages,
        "max_tokens": tokens,
    }

    # Send the request to the API
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            last_429_error_time = datetime.datetime.now()
            print("429 error encountered. Blocking requests for 15 minutes.")
            return None
        result = response.json()
    except Exception as e:
        print("Warning: API response issue", e)
        return None

    # Process the API response
    try:
        response_text = result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
        ltokens = result["usage"]["total_tokens"]
        print(f" Total tokens ${ltokens * 0.005 / 1000:.5f}")

        # Convert the response text to a JSON format
        ljson = {}
        start_time = int(time.time())
        for line in re.findall(r"(.+?)(?:[\t\n]|$)", response_text, flags=re.DOTALL):
            line = line.replace("**", "").strip()
            line = re.sub(r"^\s?[\*\-]\s?", "", line, flags=re.DOTALL)
            if len(line) > 1:
                ljson[start_time] = line
                start_time += 5

        print("Processed response:", ljson)
        return json.dumps(ljson)
    except Exception as e:
        print("GPT response processing exception:", e)
        if response is not None:
            print("GPT response text:", response.text)
        return None
