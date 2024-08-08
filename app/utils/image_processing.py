from threading import Thread, Lock
from transformers import AutoProcessor, LlavaForConditionalGeneration
from PIL import Image
import datetime

import os, io, base64, re
import requests

from config import CHATGPT_KEY

processor = None
shared_model = None

tiny_processor = None
tiny_shared_model = None


# Create a Lock object
compare_lock = Lock()
tiny_compare_lock = Lock()
# Create a Lock object
waiting_counter = 0
tiny_waiting_counter = 0

worker_id = None # allowed worker id

'''
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    # 30gb of ram - make sure we actually have this!
    #  use psutil or something otherwise the model should downgrade or not load at all
    # todo - find ways to quantize the model
    processor = AutoProcessor.from_pretrained("llava-hf/llava-1.5-7b-hf")  
    shared_model = LlavaForConditionalGeneration.from_pretrained("llava-hf/llava-1.5-7b-hf")

    tiny_processor = AutoProcessor.from_pretrained("bczhou/tiny-llava-v1-hf")
    tiny_shared_model = LlavaForConditionalGeneration.from_pretrained("bczhou/tiny-llava-v1-hf")

    worker_id = os.getpid()
'''


class TinyLLaVAComparison:

    def tiny_compare_images(self, prompt, image_paths, max_size=1280):
        # Load images
        images = [Image.open(path) for path in image_paths[-2:]]

        # Resize images while preserving aspect ratio
        resized_images = []
        for img in images:
            # should only be two images! 
            aspect_ratio = img.width / img.height
            new_width = int(aspect_ratio * max_size)
            new_height = max_size
            resized_images.append(img.resize((new_width, new_height)))

        # Stitch images together side by side
        total_width = sum(img.width for img in resized_images)
        stitched_image = Image.new('RGB', (total_width, max_size))
        x_offset = 0
        for img in resized_images:
            stitched_image.paste(img, (x_offset, 0))
            x_offset += img.width

        # Preprocess the stitched image

        global tiny_processor, tiny_shared_model
        if tiny_processor is None:
            tiny_processor = AutoProcessor.from_pretrained("bczhou/tiny-llava-v1-hf")
        if shared_model is None:
            tiny_shared_model = LlavaForConditionalGeneration.from_pretrained("bczhou/tiny-llava-v1-hf")

        if len(images) > 1:
            prompt = '<sys>Say "Interesting" if the there are differences in the splitscreen image in the context of the user prompt. Briefly describe the image in the context of the prompt in one sentence. (All timestamps UTC) </sys>\n<image>\nUSER: ' + prompt + '\nASSISTANT:'
        else:
            prompt = '<sys>Briefly describe the image in the context of the prompt in one sentence (All timestamps UTC) </sys>\n<image>\nUSER: ' + prompt + '\nASSISTANT:'


        inputs = tiny_processor(text=prompt, images=stitched_image, return_tensors="pt")

        # Generate comparison
        ldec = ''
        try:
            generate_ids = tiny_shared_model.generate(**inputs, do_sample=True, max_new_tokens=1)
            ldec = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        except Exception as e:
            print("warning!", e)

        return ldec

class LLaVAComparison:
    def compare_images(self, prompt, image_paths, max_size=1280):
        # Load images
        images = [Image.open(path) for path in image_paths[-2:]]

        # Resize images while preserving aspect ratio
        resized_images = []
        for img in images:
            # should only be two images! 
            aspect_ratio = img.width / img.height
            new_width = int(aspect_ratio * max_size)
            new_height = max_size
            resized_images.append(img.resize((new_width, new_height)))

        # Stitch images together side by side
        total_width = sum(img.width for img in resized_images)
        stitched_image = Image.new('RGB', (total_width, max_size))
        x_offset = 0
        for img in resized_images:
            stitched_image.paste(img, (x_offset, 0))
            x_offset += img.width

        # Preprocess the stitched image

        global processor, shared_model
        if processor is None:
            processor = AutoProcessor.from_pretrained("llava-hf/llava-1.5-7b-hf")
        if shared_model is None:
            shared_model = LlavaForConditionalGeneration.from_pretrained("llava-hf/llava-1.5-7b-hf")

        if len(images) > 1:
            #prompt = '<sys>You are a world-class assistant analyst with uncanny attention to detail known for brevity. Highlight the differences between the side-by-side before-and-after screen capture. Say "Interesting" if you think this should be raised to a level-two analyst. (All timestamps UTC) </sys>\n<image>\nUSER: ' + prompt + '\nASSISTANT:'
            prompt = '<sys>Say "Interesting" if the there are differences in the splitscreen image in the context of the user prompt. Briefly describe the image in the context of the prompt in one sentence. (All timestamps UTC) </sys>\n<image>\nUSER: ' + prompt + '\nASSISTANT:'
        else:
            #prompt = '<sys>You are a world-class assistant analyst with uncanny attention to detail known for brevity. Say "Interesting" if you think this should be raised to a level-two analyst. (All timestamps UTC) </sys>\n<image>\nUSER: ' + prompt + '\nASSISTANT:'
            prompt = '<sys>Briefly describe the image in the context of the prompt in one sentence (All timestamps UTC) </sys>\n<image>\nUSER: ' + prompt + '\nASSISTANT:'


        inputs = processor(text=prompt, images=stitched_image, return_tensors="pt")

        # Generate comparison
        ldec = ''
        try:
            generate_ids = shared_model.generate(**inputs, do_sample=True, max_new_tokens=16)
            ldec = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        except Exception as e:
            print("warning!", e)

        return ldec


def llava_compare(image_paths, prompt):
    #print("Comparing...", image_paths, prompt)
    global worker_id
    if worker_id != os.getpid():
        return None
    

    global waiting_counter

    # Check if all images exist
    for limage in image_paths:
        if not os.path.exists(limage):
            return 'Missing image'

    if waiting_counter > 0:
        #print(" Warning - caption busy...")
        return None # couldnt get a lock

    waiting_counter += 1

    # Try to acquire the lock with a timeout of 60 seconds
    result = ''
    tiny_result = ''
    if compare_lock.acquire(timeout=60):
        llava_comparison = LLaVAComparison()
        try:
            result = llava_comparison.compare_images(prompt, image_paths)
        finally:
            compare_lock.release()
            waiting_counter -= 1
    else:
        waiting_counter -= 1
        #print("Lock acquisition timed out")
        return None

    lresult = ''
    for leach in re.findall(r'ASSISTANT: ["]?(.+)', result, flags=re.I):
        lresult = leach
        #print("  base:", leach, image_paths[-1])

    # You can write the result to logging as needed
    #print("Prompt:", prompt, "\nResult:", lresult, "\nImages:", image_paths[-1])
    return lresult



def tiny_llava_compare(image_paths, prompt):
    #print("Comparing...", image_paths, prompt)

    global worker_id
    if worker_id != os.getpid():
        return None

    global tiny_waiting_counter

    # Check if all images exist
    for limage in image_paths:
        if not os.path.exists(limage):
            return 'Missing image'

    if tiny_waiting_counter > 0:
        #print(" Warning - caption busy...")
        return None # couldnt get a lock

    tiny_waiting_counter += 1

    # Try to acquire the lock with a timeout of 60 seconds
    tiny_result = ''
    if tiny_compare_lock.acquire(timeout=60):
        try:
            llava_comparison = TinyLLaVAComparison()
            tiny_result = llava_comparison.tiny_compare_images(prompt, image_paths)
            for leach in re.findall(r'ASSISTANT: ["]?(.+)', tiny_result, flags=re.I):
                tiny_result = leach
            #print("  tiny:", tiny_result, image_paths[-1])
        finally:
            tiny_compare_lock.release()
            tiny_waiting_counter -= 1
    else:
        tiny_waiting_counter -= 1
        #print("Lock acquisition timed out")
        return None

    # You can write the result to logging as needed
    #print("Prompt:", prompt, "\nResult:", lresult, "\nImages:", image_paths[-1])
    return tiny_result


last_429_error_time = None

class ChatGPTImageComparison:
    def __init__(self):
        self.api_key = CHATGPT_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        self.url = "https://api.openai.com/v1/chat/completions"

    def compare_images(self, prompt, image_paths, max_size=512, low_res=False, tokens=48):

        global last_429_error_time
        # Check if a 429 error occurred in the last 30 minutes
        if last_429_error_time and (datetime.datetime.now() - last_429_error_time) < datetime.timedelta(minutes=15):
            #print("Request blocked due to a recent 429 error.")
            return None

        detail = "high"
        if low_res is True:
            detail = "low"

        #if len(image_paths) > 1:
        #    prompt = 'You are a world-class analyst with uncanny attention to detail. Highlight the differences between the side-by-side before-and-after screen capture. ' + prompt 
        #else:
        #    prompt = 'You are a world-class analyst with uncanny attention to detail. ' + prompt
        #prompt = 'You are a world-class analyst with uncanny attention to detail. ' + prompt

        # Load, downsample while preserving aspect ratio, and convert images to base64
        messages = [{"role": "system", "content": [{"type": "text", 
            #"text": "You are a world-class caption writer with uncanny attention to detail.  Give us one brief insight into the content of the screenshot. Do not describe the image, say what it means in 16 words or less."
            "text": "Provide a concise, insightful observation about this image. Focus on unique or significant aspects. Limit your response to 16 words or less. Do not describe the scene, describe the anomalies. Do not be concerned about timestamp issues (the image may have local and UTC timestamps on it). Provide a concise caption in 10 words o less, focusing only on the noteable aspects.  Avoid general descriptions. Keep it short!  Then, on a newline, write a couple sentences with a more detailed description. The time is %s UTC" % datetime.datetime.utcnow()
            }]}]
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
                base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": f"{detail}"
                        }
                    }]
                })
                break

        # Construct the payload with the prompt and images
        payload = {
            #"model": "gpt-4-vision-preview",
            "model": "gpt-4-turbo", # cheaper and faster
            "messages": messages,
            "max_tokens": tokens # might even be less
        }

        # Send the request to the API
        result = None
        try:
            response = requests.post(self.url, headers=self.headers, json=payload)
            if response.status_code == 429:
                last_429_error_time = datetime.datetime.now()
                print("429 error encountered. Blocking requests for 30 minutes.")
                print(">>>", response.text)
                return None
            result = response.json()
        except Exception as e:
            print(" warning! response issue", e)

        # Process the response
        # For demonstration, we'll just return the text response
        try:
            response_text = result['choices'][0]['message']['content'].replace('\n\n','\t').strip()
            ltokens = result['usage']['total_tokens']
            # TODO: logging.. 
            print(" total tokens $%0.5f" % ( ltokens * 0.01 / 1000), 'images:', len(image_paths), image_paths[-1])
            # TODO: store the result , we paid for it
            return response_text
        except Exception as e:
            #print(" gpt exception", e, response)
            #if response is not None:
            #    print(" gpt exception text:", response.text)
            pass


def chatgpt_compare(image_paths, prompt):

    # Check if all images exist
    for image in image_paths:
        if not os.path.exists(image):
            return 'Missing image'

    # Use the ChatGPT API for comparison

    chatgpt_comparison = ChatGPTImageComparison()
    result = chatgpt_comparison.compare_images(prompt, image_paths)

    # You can write the result to logging as needed
    return result

