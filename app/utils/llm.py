import datetime
import json
import re
import time

import requests
import anthropic

from app.config import CHATGPT_KEY, ANTHROPIC_API_KEY, AVAILABLE_LLM_MODELS, DEFAULT_LLM_MODEL, LLM_SUMMARY_PROMPT

last_429_error_time = None


def summarize(prompt, history=None, tokens=4096, model=DEFAULT_LLM_MODEL):

    # 4096 kind of hte max

    global last_429_error_time
    # Check if a 429 error occurred in the last 30 minutes
    if last_429_error_time and (
        datetime.datetime.now() - last_429_error_time
    ) < datetime.timedelta(minutes=15):
        # print("Request blocked due to a recent 429 error.")
        return None

    lsummary_prompt = LLM_SUMMARY_PROMPT
    lsummary_prompt = lsummary_prompt.replace("$datetime", str(datetime.datetime.now()))

    messages = [
        {"role": "system", "content": lsummary_prompt},
        {"role": "user", "content": prompt}
    ]
    if history:
        messages.append({
            "role": "user",
            "content": "Also, please note the previous transcripts. Try to build on the history if you can, without repeating the older content. \n: " + history
        })

    if model.startswith("gpt"):
        return summarize_openai(messages, tokens, model)
    elif model.startswith("claude"):
        return summarize_anthropic(messages, tokens, model)
    else:
        raise ValueError(f"Unsupported model: {model}")

def summarize_openai(messages, tokens, model):
    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": tokens,
    }

    result = None
    response = None
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            global last_429_error_time
            last_429_error_time = datetime.datetime.now()
            print("429 error encountered. Blocking requests for 30 minutes.")
            return None
        result = response.json()
    except Exception as e:
        print(" warning! response issue", e)
        return None

    try:
        response_text = result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
        ltokens = result["usage"]["total_tokens"]
        print(f" total tokens ${ltokens * 0.005 / 1000:.5f}")

        return process_response(response_text)
    except Exception as e:
        print(" gpt exception", e, response)
        return None

def summarize_anthropic(messages, tokens, model):
    client = anthropic.Client(api_key=ANTHROPIC_API_KEY)

    prompt = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

    try:
        response = client.completion(
            model=model,
            prompt=prompt,
            max_tokens_to_sample=tokens,
        )
        return process_response(response.completion)
    except Exception as e:
        print(" anthropic exception", e)
        return None

def process_response(response_text):
    ljson = {}
    start_time = int(time.time())
    for line in re.findall(r"(.+?)(?:[\t\n]|$)", response_text, flags=re.DOTALL):
        line = line.replace("**", "")
        line = re.sub("^\s?[\*\-]\s?", "", line, flags=re.DOTALL)
        line = line.strip()
        if len(line) > 1:
            ljson[start_time] = line
            start_time += 5

    print(">>>", ljson)
    return json.dumps(ljson)
