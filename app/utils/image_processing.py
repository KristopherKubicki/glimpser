# app/utils/image_processing.py

import base64
import datetime
import io
import os

import requests
from PIL import Image

from app.config import CHATGPT_KEY, LLM_CAPTION_PROMPT, LLM_MODEL_VERSION

last_429_error_time = None

class ChatGPTImageComparison:
    """
    A class for comparing images using the ChatGPT API.
    This class handles the image processing, API communication, and response handling.
    """

    def __init__(self):
        self.api_key = CHATGPT_KEY
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.url = "https://api.openai.com/v1/chat/completions"

    def compare_images(
        self, prompt, image_paths, max_size=512, low_res=False, tokens=48
    ):
        """
        Compare images using the ChatGPT API.

        Args:
            prompt (str): The text prompt to send with the images.
            image_paths (list): List of paths to the images to be compared.
            max_size (int): Maximum size for image resizing.
            low_res (bool): If True, use low resolution detail for API request.
            tokens (int): Maximum number of tokens for the API response.

        Returns:
            str: The processed response from the API, or None if an error occurs.
        """

        global last_429_error_time
        # Check if a 429 error occurred in the last 15 minutes
        if last_429_error_time and (
            datetime.datetime.now() - last_429_error_time
        ) < datetime.timedelta(minutes=15):
            # print("Request blocked due to a recent 429 error.")
            return None

        detail = "high"
        if low_res is True:
            detail = "low"

        # Prepare messages for the API request
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": LLM_CAPTION_PROMPT}],
            }
        ]
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})

        # Process and encode images
        for image_path in reversed(image_paths):
            if not os.path.exists(image_path):
                continue
            with Image.open(image_path).convert("RGB") as img:
                # Resize image while preserving aspect ratio
                ratio = min(max_size / img.size[0], max_size / img.size[1])
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img_resized = img.resize(new_size)

                # Convert image to base64
                buffer = io.BytesIO()
                img_resized.save(buffer, format="JPEG")
                base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

                # Add image to messages
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

        # Construct the payload for the API request
        payload = {
            "model": LLM_MODEL_VERSION,
            "messages": messages,
            "max_tokens": tokens,
        }

        # Send the request to the API
        result = None
        try:
            response = requests.post(self.url, headers=self.headers, json=payload)
            if response.status_code == 429:
                last_429_error_time = datetime.datetime.now()
                print("429 error encountered. Blocking requests for 15 minutes.")
                return None
            result = response.json()
        except Exception as e:
            print(" warning! response issue", e)

        # Process and return the API response
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
    """
    Compare images using the ChatGPT API.

    This function checks if all specified images exist, then uses the
    ChatGPTImageComparison class to compare the images using the provided prompt.

    Args:
        image_paths (list): A list of file paths to the images to be compared.
        prompt (str): The text prompt to send with the images for comparison.

    Returns:
        str: The result of the image comparison, or "Missing image" if any image is not found.
    """

    # Check if all images exist
    for image in image_paths:
        if not os.path.exists(image):
            return "Missing image"

    # Use the ChatGPT API for comparison
    if len(CHATGPT_KEY) < 1: # TODO validate better
        return "Missing ChatGPT key"

    chatgpt_comparison = ChatGPTImageComparison()
    result = chatgpt_comparison.compare_images(prompt, image_paths)

    # You can write the result to logging as needed
    return result
