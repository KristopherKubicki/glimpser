# utils/screenshots.py

import datetime
import io
import ipaddress
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlparse
import glob
import shlex

import numpy as np
import requests
import undetected_chromedriver as uc
import urllib3
import yt_dlp as youtube_dl
from pdf2image import convert_from_path
from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageOps,
    ImageStat,
)
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from pynput import mouse, keyboard

logging.getLogger("webdriver_manager").setLevel(logging.WARNING)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app.config import (
    DEBUG, LANG, SCREENSHOT_DIRECTORY, UA, FFMPEG_PATH,
    NUM_FRAMES, CAPTURE_TIMEOUT, PROBE_SIZE_DEFAULT,
    PROBE_SIZE_RTSP, PROBE_SIZE_OTHER
)

last_camera_test = {}
last_camera_test_time = {}
last_camera_header = {}
last_camera_header_time = {}
last_camera_light = {}
last_camera_light_time = {}
lurl_cache = {}
lurl_cache_time = {}
throttle_cache = {}

# Global flag to track user activity
user_active = False

# Callback functions to update activity state
def on_move(x, y):
    global user_active
    user_active = True

def on_click(x, y, button, pressed):
    global user_active
    user_active = True

def on_scroll(x, y, dx, dy):
    global user_active
    user_active = True

def on_press(key):
    global user_active
    user_active = True


# Function to detect user activity
def check_user_activity(timeout=10):
    global user_active
    user_active = False

    # Create listeners for keyboard and mouse
    mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    keyboard_listener = keyboard.Listener(on_press=on_press)

    # Start listeners
    mouse_listener.start()
    keyboard_listener.start()

    # Monitor for a defined timeout
    start_time = time.time()
    while time.time() - start_time < timeout:
        if user_active:
            break
        time.sleep(0.1)

    # Stop listeners
    mouse_listener.stop()
    keyboard_listener.stop()

    return user_active


def remove_background(image, background_color=(14, 14, 14, 255), threshold=10):
    """Crop the image to remove the background color border and ensure a 16:9 aspect ratio."""
    # Find the bounding box of the non-background area
    bbox = find_bounding_box(image, background_color, threshold)

    # Adjust the bounding box to fit a 16:9 aspect ratio
    if bbox:
        bbox = adjust_bbox_to_aspect_ratio(bbox, image.size, aspect_ratio=(16, 9))
        image = image.crop(bbox)
    return image


def find_bounding_box(image, background_color=(14, 14, 14, 255), threshold=10):
    """Find the bounding box of the non-background area."""
    pixels = image.load()
    width, height = image.size
    left = width
    top = height
    right = 0
    bottom = 0

    # Go through all pixels and find the bounds of the non-background area
    for x in range(width):
        for y in range(height):
            if not is_similar_color(pixels[x, y], background_color, threshold):
                # Update the bounding box dimensions
                if x < left:
                    left = x
                if y < top:
                    top = y
                if x > right:
                    right = x
                if y > bottom:
                    bottom = y

    return (left, top, right, bottom)


def adjust_bbox_to_aspect_ratio(bbox, image_size, aspect_ratio=(16, 9)):
    """Adjust the bounding box to fit the specified aspect ratio."""
    left, top, right, bottom = bbox
    bbox_width = right - left
    bbox_height = bottom - top
    if bbox_height == 0:
        bbox_height = 1

    bbox_aspect_ratio = bbox_width / bbox_height

    target_aspect_ratio = aspect_ratio[0] / aspect_ratio[1]

    if bbox_aspect_ratio > target_aspect_ratio:
        # The bounding box is too wide, adjust the height
        new_height = bbox_width / target_aspect_ratio
        vertical_padding = (new_height - bbox_height) / 2
        top = max(0, top - vertical_padding)
        bottom = min(image_size[1], bottom + vertical_padding)
    elif bbox_aspect_ratio < target_aspect_ratio:
        # The bounding box is too tall, adjust the width
        new_width = bbox_height * target_aspect_ratio
        horizontal_padding = (new_width - bbox_width) / 2
        left = max(0, left - horizontal_padding)
        right = min(image_size[0], right + horizontal_padding)

    return (int(left), int(top), int(right), int(bottom))


def is_similar_color(color1, color2, threshold):
    """Check if two colors are similar."""
    return all(abs(c1 - c2) <= threshold for c1, c2 in zip(color1, color2))


def is_mostly_blank(image, threshold=0.92, blank_color=(255, 255, 255)):
    """
    Analyze the image to check if it's mostly blank, contains shapes, and if it's dark or light.

    :param image: PIL Image object.
    :return: A dictionary with analysis results.
    """
    # Convert the image to RGB mode
    image = image.convert("RGB")

    # Convert the image to an array
    image_array = np.array(image)

    # Check if the image is mostly blank
    blank_color = (255, 255, 255)
    blank_pixels = np.sum(np.all(np.abs(image_array - blank_color) <= 30, axis=-1))
    blank_fraction = blank_pixels / (image_array.shape[0] * image_array.shape[1])

    is_blank = blank_fraction >= threshold
    if is_blank:
        # print("    blank", blank_fraction)
        return True

    # Check for shapes by looking at the standard deviation of pixel values
    std_dev = np.std(image_array)
    has_shapes = std_dev > 20  # Adjust this threshold as needed
    if has_shapes is False:
        # print("    shapes", std_dev)
        return True

    # Check if the image is dark or light
    brightness = ImageStat.Stat(image).mean[0]
    is_dark = brightness < 10
    if is_dark:
        # print("    dark", is_dark)
        return True
    return False


def add_timestamp(image_path, name="unknown", invert=False):
    if os.path.exists(image_path):
        with Image.open(
            image_path
        ) as image:  # consider unlinking if this fails to open
            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            try:
                image = image.convert("RGB")
            except Exception as e:
                # for debugging only, otherwise unlink the file
                if DEBUG:
                    os.rename(image_path, image_path.replace(".png", ".broken"))
                else:
                    # unlink the offending image
                    os.unlink(image_path)
                # print(" warning : image load issue:", image_path, e)
                logging.error(f"Error saving image: {image_path} {e}")
                return

            # Create an ImageDraw object
            draw = ImageDraw.Draw(image)
            # if the image has the "invert" flag, then inverse this image for better readability
            if invert:
                image = ImageOps.invert(image)

            # Define the timestamp format
            timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # Define font size as 5% of the screen height
            max_height = min(image.height, image.width * 9 // 16)
            font_size = int(max_height * 0.05)
            if font_size < 5:  # anything less than a font size of 5 is goign to fail
                return

            top_offset = (image.height - max_height) / 2

            # Define font (you may need to specify a full path to a .ttf file on your system)
            try:
                font = ImageFont.truetype("Arial.ttf", font_size)
            except IOError:
                try:
                    font = ImageFont.truetype("LiberationSans-Regular.ttf", font_size)
                except IOError:
                    font = ImageFont.load_default()

            # Calculate text size and position
            text_w = int(draw.textlength(name, font=font))
            text_h = font_size
            x, y = int(10), int(10 + top_offset)
            # Create a black transparent rectangle as the background
            background = Image.new(
                "RGBA", (text_w + 20, text_h + 10), (0, 0, 0, 64)
            )  # 50% transparent black
            image.paste(background, (x - 10, y - 5), background)
            # Draw the timestamp in white text on the black transparent box
            draw.text((x, y), name, font=font, fill=(255, 255, 255, 255))  # White tex

            # Calculate text size and position
            text_w = int(draw.textlength(timestamp, font=font))
            text_h = font_size
            x, y = int(image.width - text_w - 10), int(
                image.height - top_offset - font_size * 2
            )
            # Create a black transparent rectangle as the background
            background = Image.new(
                "RGBA", (text_w + 20, text_h + 10), (0, 0, 0, 64)
            )  # 50% transparent black
            image.paste(background, (x - 10, y - 5), background)

            # Draw the timestamp in white text on the black transparent box
            draw.text(
                (x, y), timestamp, font=font, fill=(255, 255, 255, 255)
            )  # White text

            # Save the image
            image.save(image_path, "PNG")


def download_image(
    url, output_path, timeout=CAPTURE_TIMEOUT, name="unknown", invert=False, dark=False
):
    """Attempt to download an image directly from the URL and convert it to PNG format."""

    # ideally the timeout should be pretty high, its an image, and it could be real big
    if timeout < 10:
        timeout = 10

    response = None
    try:
        headers = {"user-agent": UA}
        # TODO: apply proxy here

        auth = None
        for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
            auth = requests.auth.HTTPBasicAuth(leach[0], leach[1])

        # TODO: cache the response status_code
        response = requests.get(
            url, stream=True, timeout=(timeout, timeout*3), verify=False, headers=headers, auth=auth
        )
        if (
            response.status_code == 401 and auth is not None
        ):  # Unauthorized, try Digest Authentication
            for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                auth = requests.auth.HTTPDigestAuth(leach[0], leach[1])
            response = requests.get(
                url,
                stream=True,
                timeout=(timeout,timeout*3),
                verify=False,
                headers=headers,
                auth=auth,
            )

        if response.status_code == 200:
            # Open the image directly from the response bytes
            image = Image.open(io.BytesIO(response.content))
            response.close()

            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            image = image.convert("RGB")
            image = remove_background(image)
            if dark:
                apply_dark_mode(image)
            # Save the image in PNG format
            image.save(output_path, "PNG")
            if os.path.exists(output_path):
                add_timestamp(output_path, name=name, invert=invert)
                return True
        else:
            response.close()
            logging.warning(
                f"Error downloading image: HTTP status code {response.status_code} {url}"
            )
    except Exception as e:
        logging.error(f"Error downloading image: {e} {url} {timeout}")
    finally:
        if response is not None:
            response.close()  # Ensure the connection is closed

    return False


def download_pdf(
    url, 
    output_path, 
    timeout=CAPTURE_TIMEOUT, 
    name="unknown", 
    invert=False, 
    dark=False
):
    """
    Attempt to download the first page of a PDF from the URL and convert it to PNG format.
    """
    tmp_name = None  # path of the downloaded PDF
    lsuccess = False

    if timeout < 10:
        timeout = 10

    try:
        # Download the PDF file
        headers = {"user-agent": UA}
        auth = None
        for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
            auth = requests.auth.HTTPBasicAuth(leach[0], leach[1])

        response = requests.get(
            url,
            stream=True,
            timeout=timeout,
            verify=False,
            headers=headers,
            auth=auth,
            allow_redirects=True,
        )

        # Possibly re-try with DigestAuth if 401
        if response.status_code == 401 and auth is not None:
            for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                auth = requests.auth.HTTPDigestAuth(leach[0], leach[1])
            response = requests.get(
                url,
                stream=True,
                timeout=timeout,
                verify=False,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )

        if response.status_code != 200:
            logging.error(f"Error downloading PDF: HTTP {response.status_code}")
            return False

        # Save PDF to a temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_name = tmp.name
            tmp.write(response.content)

        # Convert the first page to an image
        pages = convert_from_path(tmp_name, first_page=1, last_page=1)
        if not pages:
            logging.error("Error converting PDF to image: No pages found")
            return False

        image = pages[0].convert("RGB")
        image = remove_background(image)
        if dark:
            image = apply_dark_mode(image)
        image.save(output_path, "PNG")

        if os.path.exists(output_path):
            add_timestamp(output_path, name=name, invert=invert)
            logging.info(f"Successfully saved PDF page to {output_path}")
            lsuccess = True
        return lsuccess

    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        return False

    finally:
        # Always remove leftover PDF, unless you specifically want to keep it
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass

def is_enhanced(url):
    extractors = youtube_dl.extractor.gen_extractors()
    for e in extractors:
        if e.suitable(url) and e.IE_NAME != "generic":
            return True
    return False


def get_arp_output(ip_address, timeout):
    if platform.system() == "Windows":
        command = ["arp", "-a", ip_address]
    else:
        command = ["ip", "neigh", "show", ip_address]
    return subprocess.check_output(command, stderr=subprocess.STDOUT, timeout=timeout)


def is_private_ip(ip_address):
    return ipaddress.ip_address(ip_address).is_private


def is_address_reachable(address, port=80, timeout=5):

    if port is None:
        port = 80

    if timeout < 3:
        timeout = 3

    try:
        # Resolve the domain name to an IP address
        ip_address = socket.gethostbyname(address)
        # print(f"{address} resolved to {ip_address}")
    except Exception:
        # print(f"DNS resolution failed for {address}", e)
        return False

    # check the arp table, particularly if its an unroutable ip address
    if is_private_ip(ip_address):
        try:
            arp_entry = get_arp_output(ip_address, timeout).lower()
            if "no entry" in arp_entry.decode().lower():
                print(" warning! failing arp entry for ", ip_address)
                return False
        except Exception as e:
            print(" warning -- failure to arp", e)

    try:
        # Create a socket object
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        # Attempt to connect to the address on the specified port
        result = sock.connect_ex((ip_address, port))
        sock.close()
        if result == 0:
            # print(f"Successfully connected to {ip_address} on port {port}")
            # print(f"Failed to connect to {ip_address} on port {port}")

            return True
        return False
    except Exception as e:
        logging.warning(f"Socket error: {e}")

    return False


def parse_url(url):
    parsed_url = urlparse(url)
    domain = parsed_url.hostname
    if parsed_url and parsed_url.scheme == '' and domain is None:
        domain = re.sub(r'\/.+?$','', parsed_url.path)

    port = parsed_url.port
    # If the port is None and the scheme is specified, infer the default port
    if port is None:
        if parsed_url.scheme == "http":
            port = 80
        elif parsed_url.scheme == "https":
            port = 443
        # Add more schemes and their default ports if necessary

    return domain, port

def capture_or_download(name: str, template: str) -> bool:
    """
    Decides whether to download the image directly or capture a screenshot based on the given template.

    This function is the main entry point for capturing or downloading content from a URL. It handles
    various types of content (images, PDFs, video streams, web pages) and uses different methods to
    obtain the content based on the URL and content type.

    Args:
        name (str): The name to be used for the output file.
        template (str): A dictionary containing configuration parameters for the capture/download.

    Returns:
        bool: True if the capture/download was successful, False otherwise.
    """
    if name is None or template is None:
        return False


    global lurl_cache, lurl_cache_time, throttle_cache
    # Extract parameters from the template
    url = template.get("url")
    if throttle_cache.get(url) and throttle_cache[url].get('timeout',0) > time.time():
        # just skip things that are obviously broken.  "Backoff".. 
        return False
    if lurl_cache.get(url,'none') != "good" and time.time() - lurl_cache_time.get(url,0) < 3600: # try every 1 hour no matter what??
        return False

    popup_xpath = template.get("popup_xpath")
    dedicated_selector = template.get("dedicated_xpath")
    timeout = int(template.get("timeout", 30) or 30)

    # Set flags based on template parameters
    invert = template.get("invert", "") not in ["", "false", False]
    headless = template.get("headless", "") not in ["", "false", False]
    dark = template.get("dark", "") not in ["", "false", False]
    stealth = template.get("stealth", "") not in ["", "false", False]
    browser = template.get("browser", "") not in ["", "false", False] or stealth
    danger = template.get("danger", "") not in ["", "false", False]

    if danger:
        browser = True
        headless = True
    if not headless:
        browser = True

    # Check if the host is reachable
    domain, port = parse_url(url)
    if not is_address_reachable(domain, port=port):
        logging.debug(f"Could not reach host: {name} {url}")
        if throttle_cache.get(url) is None:
            throttle_cache[url] = {}
            throttle_cache[url]['errors'] = 1
        else:
            if throttle_cache[url]['last'] > time.time() - 60*5: # happened in the last 5 minutes?  Error again
                throttle_cache[url]['errors'] += 1
            else:
                throttle_cache[url]['errors'] = 1
        if throttle_cache[url]['errors'] > 2:
            logging.error(f"Could not reach host: {name} {url} {throttle_cache[url]['errors']} times")
            throttle_cache[url]['timeout'] = time.time() + 60*60 # 1 hour timeout
            #print("SIT DOWN FOR 1 HOUR!", round(throttle_cache[url]['last'] - time.time()), throttle_cache[url]['errors'] , url)

        throttle_cache[url]['last'] = time.time()

        return False

    # Prepare output path
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    output_path = os.path.join(SCREENSHOT_DIRECTORY, f"{name}/{name}_{timestamp}.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Determine content type
    content_type = get_content_type(url, danger)

    # Attempt to download or capture based on content type and URL
    if is_image_url(url, content_type) and not danger:
        return download_image(url, output_path, timeout, name, invert)

    if is_pdf_url(url, content_type) and not danger:
        return download_pdf(url, output_path, timeout, name, invert)

    if is_video_stream_url(url, content_type) and not danger:
        return capture_frame_from_stream(url, output_path, timeout, name, invert)

    if is_enhanced(url) and not danger:
        return capture_frame_with_ytdlp(url, output_path, name, invert)

    # Attempt lightweight browser capture for simple web pages
    if should_use_lightweight_browser(url, dedicated_selector, popup_xpath, headless, stealth, browser, danger):
        return capture_screenshot_and_har_light(url, output_path, timeout, name, invert, template.get("proxy"), dark)

    # Fall back to full browser capture
    if re.findall(r"^https?://", url, flags=re.I):
        if not browser:
            headless = True
        return capture_screenshot_and_har(url, output_path, popup_xpath, dedicated_selector, timeout, name, invert, template.get("proxy"), headless, dark, stealth, danger)

    logging.error(f"Failed to capture or download content from {url}")
    return False

def get_content_type(url, danger):
    """
    Determine the content type of the URL.

    This function attempts to get the content type using HEAD and GET requests,
    and caches the result for an hour to reduce unnecessary requests.

    Args:
        url (str): The URL to check.
        danger (bool): If True, skip content type checking.

    Returns:
        str: The determined content type, or an empty string if not determined.
    """
    global last_camera_header, last_camera_header_time

    # Check cache first
    if (last_camera_header.get(url) and
        last_camera_header_time.get(url, 0) > time.time() - 60 * 60):
        return last_camera_header.get(url)

    if "http" not in url or danger:
        return ""

    content_type = ""
    methods = [requests.head, requests.get]

    for method in methods:
        try:
            headers = {"user-agent": UA}
            if method == requests.get:
                headers["Range"] = "bytes=0-1024"

            auth = get_auth(url)
            response = method(
                url,
                stream=True,
                timeout=5,
                verify=False,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )

            if response.status_code == 401 and auth:
                auth = get_digest_auth(url)
                response = method(
                    url,
                    timeout=5,
                    verify=False,
                    headers=headers,
                    auth=auth,
                    allow_redirects=True,
                )

            if response.status_code == 404:
                logging.info(f"Missing {url}")
                return ""

            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            break  # Exit the loop if successful
        except Exception as e:
            logging.info(f"Error {method.__name__.upper()} {url}: {e}")

    # Cache the result
    if content_type:
        last_camera_header[url] = content_type
        last_camera_header_time[url] = time.time()

    return content_type

def get_auth(url):
    """Extract and return BasicAuth from URL if present."""
    auth_match = re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url)
    return requests.auth.HTTPBasicAuth(*auth_match[0]) if auth_match else None

def get_digest_auth(url):
    """Extract and return DigestAuth from URL if present."""
    auth_match = re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url)
    return requests.auth.HTTPDigestAuth(*auth_match[0]) if auth_match else None

def is_image_url(url, content_type):
    """Check if the URL is likely to be an image."""
    image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".gif", "/picture"]
    return any(ext in url.lower() for ext in image_extensions) or "image/" in content_type

def is_pdf_url(url, content_type):
    """Check if the URL is likely to be a PDF."""
    return ".pdf" in url.lower() or "/pdf" in content_type

def is_video_stream_url(url, content_type):
    """Check if the URL is likely to be a video stream."""
    video_indicators = [".mjpg", ".mp4", ".gif", ".webp", "rtsp://", ".m3u8", ":5004/"]
    return any(ind in url.lower() for ind in video_indicators) or "video/" in content_type

def should_use_lightweight_browser(url, dedicated_selector, popup_xpath, headless, stealth, browser, danger):
    """Determine if a lightweight browser should be used for capture."""
    return (re.findall(r"^https?://", url, flags=re.I) and
            dedicated_selector in [None, ""] and
            popup_xpath in [None, ""] and
            headless and
            not stealth and
            not browser and
            not is_enhanced(url) and
            not danger)

# The rest of the functions (download_image, download_pdf, capture_frame_from_stream,
# capture_frame_with_ytdlp, capture_screenshot_and_har_light, capture_screenshot_and_har)
# should be implemented as before, with appropriate error handling and logging.

def capture_frame_with_ytdlp(url, output_path, name="unknown", invert=False):
    """
    Use yt-dlp to get the video URL, then ffmpeg to capture a single frame from that video.
    """
    # Quick check for yt-dlp
    if shutil.which("yt-dlp") is None:
        logging.warning("yt-dlp is not installed or not in the system path.")
        return False

    global lurl_cache, lurl_cache_time
    if lurl_cache.get(url,'none') != "good" and time.time() - lurl_cache_time.get(url,0) < 3600: # try every 1 hour no matter what??
        # don't keep retrying on known bad
        print("  skipping", lurl_cache[url], url)
        return False

    # TODO: consider timeouts? 

    lsuccess = False
    try:
        lurl_cache_time[url] = time.time()
        # 1) Use yt-dlp to retrieve the direct video URL
        ytdlp_command = [
            "yt-dlp",
            "--get-url",
            #"--format",
            #"bestvideo",  # note, don't specify this or it will screw up on streams without audio (common)
            url,
        ]
        result = subprocess.run(
            ytdlp_command,
            #check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Note! check the result. If the return code isnt 0, then we should fail out.  Why though? Check on that too. 

        if result.returncode != 0:
            lurl_cache[url] = "bad"
            if re.findall(r'(?:vailable|found|404)', result.stderr.decode('utf-8').lower()):
                lurl_cache[url] = "offline"
                #print("offline", url)
            #print("RESULT1", result)
            return False

        lurl_cache[url] = "good"
        video_url = result.stdout.decode().strip()
        # 2) Use ffmpeg to capture a single frame
        ffmpeg_command = [
            "ffmpeg",
            "-analyzeduration",
            "20M",
            "-probesize",
            "20M",
            "-ec",
            "15",
            "-i",
            video_url,
            "-sn",
            "-an",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "rgb24",
            "-frames:v",
            "1",
            "-fflags",
            "+igndts+ignidx+genpts+fastseek+discardcorrupt",
            "-q:v",
            "0",
            "-f",
            "image2",
            "-y",
            output_path,
        ]
        subprocess.run(
            ffmpeg_command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 3) Check output; add timestamp
        if os.path.exists(output_path):
            add_timestamp(output_path, name=name, invert=invert)
            logging.info(f"Successfully captured frame with ytdlp+ffmpeg: {url}")
            lsuccess = True

        return lsuccess

    except Exception as e:
        logging.error(f"Error capturing frame with yt-dlp and ffmpeg: {e}")
        return False

    finally:
        # If partial file was created but we didn't fully succeed, remove it
        if not lsuccess and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass


def capture_frame_from_stream(
    url, output_path, timeout=CAPTURE_TIMEOUT, name="unknown", invert=False
):
    """Use ffmpeg to capture multiple frames from a video stream and save the last one."""
    if shutil.which(FFMPEG_PATH) is None:
        print(f"{FFMPEG_PATH} is not installed or not in the system path.")
        return False

    if timeout < 5:
        timeout = 5

    with tempfile.TemporaryDirectory() as tmpdirname:  # todo make sure this gets dleted
        # Capture multiple frames into the temporary directory
        temp_output_pattern = os.path.join(tmpdirname, "frame_%03d.png")
        command = [
            FFMPEG_PATH,  # Use the configurable FFMPEG_PATH
            "-hide_banner",
            #'-hwaccel', 'auto',  #TODO add support
        ]

        probe_size = PROBE_SIZE_DEFAULT
        if "http:" in url or "https:" in url:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            command.extend(["-headers", "User-Agent: %s\r\n" % UA])
            command.extend(["-headers", f"referer: {base_url}\r\n"])
            command.extend(["-headers", f"origin: {base_url}\r\n"])
            command.extend(["-seekable", "0"])
            # command.extend(['-timeout', str(CAPTURE_TIMEOUT-1)])  # not sure why, but this causes us a lot of issues, dont set a timetout
            probe_size = PROBE_SIZE_DEFAULT
        elif "rtsp:" in url:
            command.extend(["-rtsp_transport", "tcp"])
            probe_size = PROBE_SIZE_RTSP
            if "/streaming/" in url.lower():  # alittle bit of a hack
                command.extend(["-c:v", "h264"])
                command.extend(["-r", "1"])
                probe_size = PROBE_SIZE_OTHER
        else:
            probe_size = PROBE_SIZE_OTHER

        # todo: make this configurable instead
        command.extend(["-analyzeduration", probe_size])
        command.extend(["-probesize", probe_size])
        command.extend(
            [
                "-use_wallclock_as_timestamps",
                "1",
                #'-ec', '15',
                "-threads",
                "1",
                "-skip_frame",
                "nokey",
                "-sn",
                "-an",
                #'-err_detect','aggressive',
                "-i",
                url,  # Input stream URL
                "-movflags",
                "+faststart",
                "-pix_fmt",
                "rgb24",
                "-frames:v",
                str(NUM_FRAMES),  # Capture 'NUM_FRAMES' frames
                "-fflags",
                "+igndts+ignidx+genpts+fastseek+discardcorrupt",
                "-q:v",
                "0",  # Output quality (lower is better)
                #'-b:v', '50000000',               # Output quality (lower is better)
                "-f",
                "image2",  # Force image2 muxer
                temp_output_pattern,  # Temporary output file pattern
            ]
        )

        try:
            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                )
                # print("mmm", ' '.join(command))
                # subprocess.run(command, check=True, timeout=CAPTURE_TIMEOUT)
            except Exception:
                # print("<<naye timeout...", e)
                pass

            # Sort the captured frames by size and take the last one
            frames = sorted(
                os.listdir(tmpdirname),
                key=lambda x: os.path.getsize(os.path.join(tmpdirname, x)),
            )
            if frames:
                last_frame_path = os.path.join(tmpdirname, frames[-1])
                # Move the last frame to the output path
                shutil.move(last_frame_path, output_path)
                if os.path.exists(output_path):
                    add_timestamp(output_path, name=name, invert=invert)
                    logging.info(f"Successfully captured frame from stream {url}")
                    return True
            else:
                logging.error(f"No frames captured from stream {url}")
        except Exception as e:
            logging.error(f"Error capturing frames from stream: {e}")

    logging.error(f"Error capturing frame with {FFMPEG_PATH}: {url}")
    return False



def apply_dark_mode(img, range_value=30, text_range_value=120):
    pixels = img.load()  # Get the pixel map of the image
    text_upper_bound = 255 - text_range_value

    for y in range(img.size[1]):  # Iterate over the height of the image
        for x in range(img.size[0]):  # Iterate over the width of the image
            pixel = pixels[x, y]

            if (
                0 <= pixel[0] <= text_range_value
                and 0 <= pixel[1] <= text_range_value
                and 0 <= pixel[2] <= text_range_value
            ):
                pixels[x, y] = (255 - pixel[0], 255 - pixel[1], 255 - pixel[2])
            elif (
                text_upper_bound <= pixel[0] <= 255
                and text_upper_bound <= pixel[1] <= 255
                and text_upper_bound <= pixel[2] <= 255
            ):
                pixels[x, y] = (255 - pixel[0], 255 - pixel[1], 255 - pixel[2])

    return img


def capture_screenshot_and_har_light(
    url, 
    output_path, 
    timeout=CAPTURE_TIMEOUT, 
    name="unknown", 
    invert=False, 
    proxy=None, 
    dark=True
):
    """
    Capture a screenshot of a URL using wkhtmltoimage (WebKit).
    """
    # Check if wkhtmltoimage is available
    if shutil.which("wkhtmltoimage") is None:
        logging.warning("wkhtmltoimage is not installed or not in the system path.")
        return False

    if timeout < 10:
        timeout = 10

    # We'll stage a temporary filename for the "in-progress" PNG
    tmp_path = output_path.replace(".png", ".tmp.png")
    lsuccess = False
    start_time = time.time()

    command = [
        "wkhtmltoimage",
        "--width",
        "1920",
        "--height",
        "1080",
        "--javascript-delay",
        str(5000),
        "--quiet",
        "--zoom",
        "1",
        "--quality",
        "100",
        "--enable-javascript",
        "--custom-header",
        "User-Agent",
        UA,
        "--custom-header-propagation",
        shlex.quote(url),
        shlex.quote(tmp_path),
    ]

    try:
        # Run wkhtmltoimage
        result = subprocess.run(
            command,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False
        )

        if result.returncode != 0:
            logging.warning(f"wkhtmltoimage failed (returncode {result.returncode}): {result.stderr.decode('utf-8','ignore')}")
            return False

        # Process the output file
        if not os.path.exists(tmp_path):
            return False

        # Open and convert the image
        with Image.open(tmp_path) as image:
            image = image.convert("RGB")  # ensure RGB
            if is_mostly_blank(image):
                logging.warning(f"Captured image is mostly blank—skipping. {url}")
                return False

            image = remove_background(image)
            if dark:
                image = apply_dark_mode(image)
            image.save(tmp_path, "PNG")

        # Rename from .tmp.png to final .png
        if os.path.exists(tmp_path):
            add_timestamp(tmp_path, name, invert=invert)
            os.rename(tmp_path, output_path)
            lsuccess = True

        # If you capture HAR data, do that here as well...
        logging.info(
            f"Successfully captured light screenshot for {url} at {output_path} "
            f"({round(time.time() - start_time, 3)}s)"
        )
        return lsuccess

    except Exception as e:
        logging.error(f"Error in capture_screenshot_and_har_light: {e}")
        return False

    finally:
        # Cleanup partial file if unsuccessful
        if not lsuccess and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


chrome_version = {}


def get_chrome_version(chrome_path):
    # Command to get the installed version of Chrome
    global chrome_version
    if (
        chrome_version.get(chrome_path) is not None
        and chrome_version[chrome_path][1] > time.time() - 60 * 60
    ):
        return chrome_version[chrome_path][0]

    command = "%s --version" % chrome_path
    result = subprocess.run(command.split(), capture_output=True, text=True)
    version = result.stdout.strip().split()[-1]
    version = version.split(".")[0]  # Return the major version
    chrome_version[chrome_path] = (version, time.time())
    return version


def extract_version(driver_path):
    try:
        # Extract the version using regex to handle different structures
        match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", driver_path)
        if match:
            return int(
                match.group(1)
            )  # Return the main version part (e.g., 124 from 124.0.6367.207)
        else:
            raise ValueError("Version number not found in the path.")
    except Exception as e:
        print(f"Error extracting version from path: {driver_path}, error: {e}")
        # Default to a known working version if extraction fails
        return 127


def is_port_open(host, port, timeout=5):
    """Check if a network port is open on the specified host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            print(" should close??", host)
            sock.close()
            print(" closed", host)
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False



def is_chrome_debug_port_open(host="127.0.0.1", port=9222, timeout=1):
    """
    Check if an existing Chrome with --remote-debugging-port=9222 is open.
    """
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


#################################################
# Main function with Danger mode & Stealth mode #
#################################################

def capture_screenshot_and_har(
    url,
    output_path,
    popup_xpath=None,
    dedicated_selector=None,
    timeout=30,
    name="unknown",
    invert=False,
    proxy=None,       # Not heavily used here, but you could insert your proxy logic
    headless=True,
    stealth=True,     # Attempt to hide headless with undetected-chromedriver
    dark=True,        # Optional post-processing
    danger=False,     # If True, attach to existing Chrome (not headless)
) -> bool:
    """
    Captures a screenshot of `url` and saves to `output_path`.

    1) Danger Mode (danger=True):
       - Attaches to an existing Chrome with --remote-debugging-port=9222.
       - Opens a new tab, loads page, screenshots, closes tab.
       - Skips if the user is active (check_user_activity).
       - Not headless (relies on the user’s Chrome).

    2) Non-Danger Mode (danger=False):
       - ALWAYS uses headless Chrome. No pop-up window on screen.
       - If `stealth` is True and `undetected_chromedriver` is available, it tries to reduce detection of headless.
       - Creates a fresh temporary Chrome user-data-dir.
       - Quits after capture.

    Returns True on success, False otherwise.
    """

    # Quick sanity check
    if not re.match(r'^https?://', url, flags=re.IGNORECASE):
        logging.error(f"Invalid or unsupported URL: {url}")
        return False

    if timeout < 10:
        timeout = 10

    tmp_screenshot = output_path + ".partial.png"
    success = False

    # Danger mode: attach to existing local Chrome on port 9222
    if danger:
        # Skip if user is active
        if check_user_activity(timeout=10):
            logging.warning("User activity detected; skipping Danger screenshot.")
            return False

        # Check if remote debug port open
        if not is_chrome_debug_port_open("127.0.0.1", 9222):
            logging.warning("Danger mode requested, but no Chrome on port 9222.")
            return False

        try:
            chrome_service = Service(ChromeDriverManager().install())

            danger_options = Options()
            # Do NOT set headless => we want to attach to the UI-based Chrome
            danger_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            danger_options.add_argument("--no-sandbox")
            danger_options.add_argument("--disable-dev-shm-usage")

            driver = webdriver.Chrome(service=chrome_service, options=danger_options)
            original_handle = driver.current_window_handle

            # Open new tab
            driver.execute_script("window.open('','_blank');")
            new_tab_handle = driver.window_handles[-1]
            driver.switch_to.window(new_tab_handle)

            # Load page
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            time.sleep(1)  # Let DOM settle

            # Remove popups if any
            if popup_xpath:
                try:
                    elements = driver.find_elements(By.XPATH, popup_xpath)
                    for e in elements:
                        driver.execute_script("arguments[0].remove();", e)
                except Exception:
                    pass

            # If dedicated selector
            if dedicated_selector:
                try:
                    el = driver.find_element(By.XPATH, dedicated_selector)
                    driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    time.sleep(1)
                    el.screenshot(tmp_screenshot)
                except Exception as e:
                    logging.warning(f"Dedicated selector error: {e}")

            # Fallback full screenshot
            if not os.path.exists(tmp_screenshot):
                driver.save_screenshot(tmp_screenshot)

            # Close new tab
            driver.close()
            driver.switch_to.window(original_handle)
            driver = None  # DO NOT quit => that closes user’s entire Chrome

            # Post-process
            if os.path.exists(tmp_screenshot):
                success = _postprocess_and_finalize(tmp_screenshot, output_path, name, invert, dark)

        except TimeoutException:
            logging.warning(f"Danger mode timed out loading page: {url}")
        except Exception as e:
            logging.error(f"Danger mode error for {url}: {e}")

        return success

    ############################################
    # Non-Danger mode => ALWAYS HEADLESS       #
    ############################################

    driver = None
    with tempfile.TemporaryDirectory() as user_data_dir:
        try:
            chrome_service = Service(ChromeDriverManager().install())

            # We'll rely on undetected_chromedriver if stealth=True and it’s installed
            if stealth and uc is not None:
                chrome_options = uc.ChromeOptions()
            else:
                chrome_options = Options()

            # Force headless in non-danger mode
            #   Use “--headless=new” for Chrome 109+ if available.
            chrome_options.add_argument("--headless=new")

            # Required minimal flags
            chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-infobars")
            #chrome_options.add_experimental_option(
            #    "excludeSwitches", ["enable-automation"]
            #)
            #chrome_options.add_experimental_option("useAutomationExtension", False)

            # If you have a proxy
            if proxy:
                chrome_options.add_argument(f"--proxy-server={proxy}")

            # Spin up the driver
            if stealth and uc is not None:
                driver = uc.Chrome(
                    service=chrome_service,
                    options=chrome_options,
                    headless=True   # (Although UC might do this automatically)
                )
            else:
                driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

            driver.set_page_load_timeout(timeout)
            driver.get(url)
            time.sleep(1)

            # Remove popup
            if popup_xpath:
                try:
                    elements = driver.find_elements(By.XPATH, popup_xpath)
                    for e in elements:
                        driver.execute_script("arguments[0].remove();", e)
                except Exception:
                    pass

            # Dedicated selector
            if dedicated_selector:
                try:
                    el = driver.find_element(By.XPATH, dedicated_selector)
                    driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    time.sleep(1)
                    el.screenshot(tmp_screenshot)
                except Exception as e:
                    logging.warning(f"Dedicated selector error: {dedicated_selector} {url}")

            # Fallback full screenshot
            if not os.path.exists(tmp_screenshot):
                driver.save_screenshot(tmp_screenshot)

            # Post-process
            if os.path.exists(tmp_screenshot):
                success = _postprocess_and_finalize(tmp_screenshot, output_path, name, invert, dark)

        except TimeoutException:
            logging.warning(f"Timed out loading page: {url}")
        except Exception as e:
            logging.error(f"Error capturing screenshot for {url}: {proxy} {e}")
        finally:
            # Clean up ephemeral driver
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    return success

##############################
# Post-processing subroutine #
##############################

def _postprocess_and_finalize(tmp_path, final_path, name, invert, dark):
    """
    Finalize screenshot:
      - Convert to RGB
      - Check blank
      - Remove background
      - Optional "dark" transformations
      - Add timestamp
      - Rename from partial to final
    """
    try:
        with Image.open(tmp_path) as img:
            img = img.convert("RGB")
            if is_mostly_blank(img):
                logging.warning(f"Captured image is mostly blank. {name}")
                #os.remove(tmp_path)
                #return False

            # Example remove background
            img = remove_background(img)

            # If "dark" transformations are needed
            if dark:
                # e.g. apply_dark_mode(img) if you have that function
                pass

            # Save
            img.save(tmp_path, "PNG")

        # Add timestamp overlay
        add_timestamp(tmp_path, name=name, invert=invert)

        # Rename to final
        os.rename(tmp_path, final_path)
        return True

    except Exception as e:
        logging.error(f"Post-process error: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False
