import base64
import datetime
import io
import os

import requests
from PIL import Image

from app.config import CHATGPT_KEY, LLM_CAPTION_PROMPT, LLM_MODEL_VERSION

last_429_error_time = None


class ChatGPTImageComparison:
    def __init__(self):
        self.api_key = CHATGPT_KEY
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.url = "https://api.openai.com/v1/chat/completions"

    def compare_images(
        self, prompt, image_paths, max_size=512, low_res=False, tokens=48
    ):

        global last_429_error_time
        # Check if a 429 error occurred in the last 30 minutes
        if last_429_error_time and (
            datetime.datetime.now() - last_429_error_time
        ) < datetime.timedelta(minutes=15):
            # print("Request blocked due to a recent 429 error.")
            return None

        detail = "high"
        if low_res is True:
            detail = "low"

        # Load, downsample while preserving aspect ratio, and convert images to base64
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": LLM_CAPTION_PROMPT}],
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

        # Send the request to the API
        result = None
        try:
            response = requests.post(self.url, headers=self.headers, json=payload)
            if response.status_code == 429:
                last_429_error_time = datetime.datetime.now()
                print("429 error encountered. Blocking requests for 30 minutes.")
                return None
            result = response.json()
        except Exception as e:
            print(" warning! response issue", e)

        # Process the response
        # For demonstration, we'll just return the text response
        try:
            response_text = (
                result["choices"][0]["message"]["content"].replace("\n\n", "\t").strip()
            )
            ltokens = result["usage"]["total_tokens"]
            # TODO: logging..
            print(
                    " total tokens $%0.5f" % (ltokens * 0.005 / 1000), # TODO: this calculation is wrong!  Figure it out?  Also log it do the db
                "images:",
                len(image_paths),
                image_paths[-1],
            )  # todo, out of date...
            # TODO: store the result , we paid for it
            return response_text
        except Exception:
            # print(" gpt exception", e, response)
            # if response is not None:
            #    print(" gpt exception text:", response.text)
            pass


def chatgpt_compare(image_paths, prompt):

    # Check if all images exist
    for image in image_paths:
        if not os.path.exists(image):
            return "Missing image"

    # Use the ChatGPT API for comparison
    if len(CHATGPT_KEY) < 1:
        return "Missing ChatGPT key"

    chatgpt_comparison = ChatGPTImageComparison()
    result = chatgpt_comparison.compare_images(prompt, image_paths)

    # You can write the result to logging as needed
    return result
