import datetime
import json
import re
import time

import requests

from app.config import CHATGPT_KEY, LLM_MODEL_VERSION, LLM_SUMMARY_PROMPT

last_429_error_time = None


def summarize(prompt, history=None, tokens=4096):
    """
    Generate a summary using a language model based on the given prompt and optional history.

    This function interacts with an AI language model (e.g., GPT) to generate summaries or responses
    based on the provided input. It handles rate limiting, error handling, and response processing.

    Args:
        prompt (str): The main text or question to be summarized or answered.
        history (str, optional): Previous conversation history to provide context. Defaults to None.
        tokens (int, optional): Maximum number of tokens for the response. Defaults to 4096.

    Returns:
        str or None: A JSON string containing the processed response, or None if an error occurred.

    Key steps in the process:
    1. Check for recent rate limit errors (429 status code)
    2. Prepare the API request with the prompt, history, and system message
    3. Send the request to the language model API
    4. Process and format the response
    5. Handle errors and exceptions

    Note:
    - The function uses global configurations like CHATGPT_KEY and LLM_MODEL_VERSION.
    - It implements a simple rate limiting mechanism to prevent excessive API calls after a 429 error.
    - The response is processed into a JSON format with timestamps for each line.

    TODO:
    - Make the summary prompt configurable via the database
    - Implement proper logging instead of print statements
    - Store the API response for future use or analysis
    - Optimize token usage and pricing calculations
    """

    global last_429_error_time
    # Check if a 429 error occurred in the last 15 minutes
    if last_429_error_time and (
        datetime.datetime.now() - last_429_error_time
    ) < datetime.timedelta(minutes=15):
        logging.warning("Request blocked due to a recent 429 error.")
        return None

    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    # Prepare the summary prompt
    lsummary_prompt = LLM_SUMMARY_PROMPT.replace("$datetime", str(datetime.datetime.now()))

    # Construct the messages for the API request
    messages = [
        {"role": "system", "content": [{"type": "text", "text": lsummary_prompt}]},
        {"role": "user", "content": [{"type": "text", "text": prompt}]}
    ]
    if history:
        messages.append({
            "role": "user",
            "content": [{
                "type": "text",
                "text": "Also, please note the previous transcripts. Try to build on the history if you can, without repeating the older content.\n: " + history,
            }],
        })

    # Prepare the API request payload
    payload = {
        "model": LLM_MODEL_VERSION,
        "messages": messages,
        "max_tokens": tokens,
    }

    # Send the request to the API and handle the response
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            last_429_error_time = datetime.datetime.now()
            logging.error("429 error encountered. Blocking requests for 15 minutes.")
            return None
        result = response.json()

        # Process the response
        response_text = result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
        ltokens = result["usage"]["total_tokens"]
        logging.info(f"Total tokens used: {ltokens} (Cost: ${ltokens * 0.005 / 1000:.5f})")

        # Convert the response to a JSON format with timestamps
        ljson = {}
        start_time = int(time.time())
        for line in re.findall(r"(.+?)(?:[\t\n]|$)", response_text, flags=re.DOTALL):
            line = line.replace("**", "").strip()
            line = re.sub(r"^\s?[\*\-]\s?", "", line, flags=re.DOTALL)
            if len(line) > 1:
                ljson[start_time] = line
                start_time += 5

        logging.debug(f"Processed response: {ljson}")
        return json.dumps(ljson)

    except Exception as e:
        logging.error(f"Error in API request or response processing: {e}")
        if response is not None:
            logging.error(f"API response text: {response.text}")
        return None
