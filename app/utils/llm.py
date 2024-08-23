import datetime
import json
import re
import time
import logging

import requests
from sqlalchemy import Column, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError

from app.config import CHATGPT_KEY, LLM_MODEL_VERSION, LLM_SUMMARY_PROMPT
from app.database import SessionLocal, Base

Base = declarative_base()

class LLMResult(Base):
    __tablename__ = "llm_results"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    content = Column(Text)

last_429_error_time = None


def summarize(prompt, history=None, tokens=4096):

    # 4096 kind of hte max

    global last_429_error_time
    # Check if a 429 error occurred in the last 30 minutes
    if last_429_error_time and (
        datetime.datetime.now() - last_429_error_time
    ) < datetime.timedelta(minutes=15):
        # print("Request blocked due to a recent 429 error.")
        return None

    headers = {"Authorization": f"Bearer {CHATGPT_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    # TODO: make this configurable by the database instead

    lsummary_prompt = LLM_SUMMARY_PROMPT
    lsummary_prompt.replace("$datetime", str(datetime.datetime.now()))

    messages = [
        {"role": "system", "content": [{"type": "text", "text": lsummary_prompt}]}
    ]
    messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
    if history:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Also, please note the previous transcripts.  Try to build on the history if you can, without repeating the older content. \n: "
                        + history,
                    }
                ],
            }
        )

    # Construct the payload with the prompt and images
    payload = {
        "model": LLM_MODEL_VERSION,  # cheaper and faster
        "messages": messages,
        "max_tokens": tokens,  # might even be less
    }

    # Send the request to the API
    result = None
    response = None
    try:
        response = requests.post(url, headers=headers, json=payload)
        logging.debug(f"Response text: {response.text}")
        if response.status_code == 429:
            last_429_error_time = datetime.datetime.now()
            logging.warning("429 error encountered. Blocking requests for 30 minutes.")
            return None
        result = response.json()
    except Exception as e:
        logging.warning(f"Warning! Response issue: {e}")

    # Process the response
    try:
        response_text = (
            result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
        )
        ltokens = result["usage"]["total_tokens"]
        logging.info(f"Total tokens: ${ltokens * 0.005 / 1000:.5f}")

        ljson = {}
        start_time = int(time.time())
        for line in re.findall(r"(.+?)(?:[\t\n]|$)", response_text, flags=re.DOTALL):
            line = line.replace("**", "")
            line = re.sub("^\s?[\*\-]\s?", "", line, flags=re.DOTALL)
            line = line.strip()
            if len(line) > 1:
                ljson[start_time] = line
                start_time += 5

        logging.debug(f"Processed JSON: {ljson}")
        
        # Store the result
        self.store_result(ljson)
        
        return json.dumps(ljson)
    except Exception as e:
        logging.error(f"GPT exception: {e}")
        if response is not None:
            logging.error(f"GPT exception text: {response.text}")
        pass

def store_result(result):
    """
    Store the LLM result in the database.

    :param result: The result to store
    """
    try:
        session = SessionLocal()
        new_result = LLMResult(
            timestamp=datetime.datetime.utcnow(),
            content=json.dumps(result)
        )
        session.add(new_result)
        session.commit()
        logging.info(f"Stored LLM result with ID: {new_result.id}")
    except SQLAlchemyError as e:
        logging.error(f"Failed to store LLM result: {e}")
        session.rollback()
    finally:
        session.close()
