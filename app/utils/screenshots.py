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
from typing import List, Tuple, Dict, Optional, Union, Any

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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app.config import DEBUG, LANG, SCREENSHOT_DIRECTORY, UA

last_camera_test: Dict[str, Any] = {}
last_camera_test_time: Dict[str, float] = {}
last_camera_header: Dict[str, str] = {}
last_camera_header_time: Dict[str, float] = {}
last_camera_light: Dict[str, Any] = {}
last_camera_light_time: Dict[str, float] = {}


def remove_background(image: Image.Image, background_color: Tuple[int, int, int, int] = (14, 14, 14, 255), threshold: int = 10) -> Image.Image:
    """Crop the image to remove the background color border and ensure a 16:9 aspect ratio."""
    # Find the bounding box of the non-background area
    bbox = find_bounding_box(image, background_color, threshold)

    # Adjust the bounding box to fit a 16:9 aspect ratio
    if bbox:
        bbox = adjust_bbox_to_aspect_ratio(bbox, image.size, aspect_ratio=(16, 9))
        image = image.crop(bbox)
    return image


def find_bounding_box(image: Image.Image, background_color: Tuple[int, int, int, int] = (14, 14, 14, 255), threshold: int = 10) -> Tuple[int, int, int, int]:
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


def adjust_bbox_to_aspect_ratio(bbox: Tuple[int, int, int, int], image_size: Tuple[int, int], aspect_ratio: Tuple[int, int] = (16, 9)) -> Tuple[int, int, int, int]:
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


def is_similar_color(color1: Tuple[int, int, int, int], color2: Tuple[int, int, int, int], threshold: int) -> bool:
    """Check if two colors are similar."""
    return all(abs(c1 - c2) <= threshold for c1, c2 in zip(color1, color2))


def is_mostly_blank(image: Image.Image, threshold: float = 0.92, blank_color: Tuple[int, int, int] = (255, 255, 255)) -> bool:
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


def add_timestamp(image_path: str, name: str = "unknown", invert: bool = False) -> None:
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
    url: str, output_path: str, timeout: int = 30, name: str = "unknown", invert: bool = False, dark: bool = False
) -> bool:
    """Attempt to download an image directly from the URL and convert it to PNG format."""

    response = None
    try:
        headers = {"user-agent": UA}
        # TODO: apply proxy here

        auth = None
        for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
            auth = requests.auth.HTTPBasicAuth(leach[0], leach[1])
        response = requests.get(
            url, stream=True, timeout=timeout, verify=False, headers=headers, auth=auth
        )
        if (
            response.status_code == 401 and auth is not None
        ):  # Unauthorized, try Digest Authentication
            for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                auth = requests.auth.HTTPDigestAuth(leach[0], leach[1])
            response = requests.get(
                url,
                stream=True,
                timeout=timeout,
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
            logging.warn(
                f"Error downloading image: HTTP status code {response.status_code} {url}"
            )
    except Exception as e:
        logging.error(f"Error downloading image: {e} {url}")
    finally:
        if response is not None:
            response.close()  # Ensure the connection is closed

    return False


def download_pdf(
    url: str, output_path: str, timeout: int = 30, name: str = "unknown", invert: bool = False, dark: bool = False
) -> bool:
    """Attempt to download the first page of a PDF from the URL and convert it to PNG format."""

    try:
        # Download the PDF file
        headers = {"user-agent": UA}

        # TODO: apply proxy

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
        if (
            response.status_code == 401 and auth is not None
        ):  # Unauthorized, try Digest Authentication
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

        if response.status_code == 200:
            # Save the PDF to a temporary file
            tmp_name = None
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(response.content)
                tmp_name = tmp.name
            # Convert the first page of the PDF to an image
            pages = convert_from_path(tmp_name, first_page=1, last_page=1)
            if pages:
                image = pages[0]
                # Convert the image to RGBA mode in case it's a format that doesn't support transparency
                image = image.convert("RGB")
                image = remove_background(image)
                if dark:
                    apply_dark_mode(image)
                # Save the image in PNG format
                image.save(output_path, "PNG")
                if os.path.exists(output_path):
                    add_timestamp(output_path, name=name, invert=invert)
                    # Remove the temporary PDF file
                    os.remove(tmp_name)
                    return True
            else:
                logging.error("Error converting PDF to image: No pages found")
                if tmp_name and os.path.exists(tmp_name):
                    os.remove(tmp_name)
                return False
        else:
            logging.error(
                f"Error downloading PDF: HTTP status code {response.status_code}"
            )
            return False
    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        return False


def is_enhanced(url: str) -> bool:
    extractors = youtube_dl.extractor.gen_extractors()
    for e in extractors:
        if e.suitable(url) and e.IE_NAME != "generic":
            return True
    return False


def get_arp_output(ip_address: str, timeout: int) -> bytes:
    if platform.system() == "Windows":
        command = ["arp", "-a", ip_address]
    else:
        command = ["ip", "neigh", "show", ip_address]
    return subprocess.check_output(command, stderr=subprocess.STDOUT, timeout=timeout)


def is_private_ip(ip_address: str) -> bool:
    return ipaddress.ip_address(ip_address).is_private


def is_address_reachable(address: str, port: int = 80, timeout: int = 5) -> bool:

    if port is None:
        port = 80

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
        logging.warn(f"Socket error: {e}")

    return False


def parse_url(url: str) -> Tuple[Optional[str], Optional[int]]:
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


def capture_or_download(name: str, template: Dict[str, Any]) -> bool:
    """Decides whether to download the image directly or capture a screenshot."""

    if name is None or template is None:
        return False

    url = template.get("url")
    popup_xpath = template.get("popup_xpath")
    dedicated_selector = template.get("dedicated_xpath")
    timeout = int(template.get("timeout", 30) or 30)
    invert = False
    headless = False
    dark = False
    stealth = False
    browser = False
    danger = False
    if template.get("invert", "") not in ["", "false", False]:
        invert = True
    if template.get("headless", "") not in ["", "false", False]:
        headless = True
    if template.get("dark", "") not in ["", "false", False]:
        dark = True
    if template.get("stealth", "") not in ["", "false", False]:
        stealth = True
        browser = True
    if template.get("browser", "") not in ["", "false", False]:
        browser = True
    if template.get("danger", "") not in ["", "false", False]:
        danger = True
        browser = True
        headless = True
    if headless is False:
        browser = True

    # Check to see if the host is online
    domain, port = parse_url(url)
    if is_address_reachable(domain, port=port) is False:
        logging.error("Unsuccessfully could not reach host: %s %s" % (name, url))
        return False

    # TODO: let the template specify which downloader to use
    # Current datetime in the specified format
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    # Update the output_path format to include the timestamp
    output_path = os.path.join(SCREENSHOT_DIRECTORY, f"{name}/{name}_{timestamp}.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Check if the URL is reachable and get the content type
    # add a simple requests.head call to figure out what kind of media type this is, etc
    content_type = ""
    global last_camera_header, last_camera_header_time, last_camera_test, last_camera_test_time
    if (
        last_camera_header.get(url)
        and last_camera_header_time.get(url, 0) > time.time() - 60 * 60
    ):
        content_type = last_camera_header.get(url)

    if content_type == "" and "http" in url and not danger:
        try:
            headers = {"user-agent": UA}

            auth = None
            for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                auth = requests.auth.HTTPBasicAuth(leach[0], leach[1])
            response = requests.head(
                url,
                stream=True,
                timeout=5,
                verify=False,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )
            if (
                response.status_code == 401 and auth is not None
            ):  # Unauthorized, try Digest Authentication
                for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                    auth = requests.auth.HTTPDigestAuth(leach[0], leach[1])
                response = requests.head(
                    url,
                    timeout=5,
                    verify=False,
                    headers=headers,
                    auth=auth,
                    allow_redirects=True,
                )

            if response.status_code == 404:
                logging.info(f"Missing {url}")
                return False

            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            # logging.info(f"Content type for {url} is {content_type}")
        except Exception as e:
            if "unsupported" in str(e).lower():
                logging.info(f"Unsupported HEAD {url}: {e}")
            elif "method not allowed" in str(e).lower():
                logging.info(f"Not allowed HEAD {url}: {e}")
            elif "401 client error" in str(e).lower():
                logging.info(f"Error HEAD {url}: {e}")
            elif "timeout" in str(e).lower():
                logging.error(f"Error HEAD {url}: {e}")
                return False
            else:
                # however, a timeout is usually pretty bad.
                #  we generally dont even want to keep going if a timeout happens.  Consider it.

                # note - just because this error is here, doesnt actually mean the content isnt here.  cameras often dont support head()
                logging.info(f"Content type for {url}: {e}")
            # print(" warn1", response.headers)
            # really no worse off than we were before

    if content_type == "" and "http" in url and not danger:
        # Perform a range request to get a small part of the content
        try:
            headers = {"user-agent": UA, "Range": "bytes=0-1024"}
            # TODO: apply proxy

            auth = None
            for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                auth = requests.auth.HTTPBasicAuth(leach[0], leach[1])
            response = requests.get(
                url,
                stream=True,
                timeout=5,
                verify=False,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )

            if (
                response.status_code == 401 and auth is not None
            ):  # Unauthorized, try Digest Authentication
                for leach in re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url):
                    auth = requests.auth.HTTPDigestAuth(leach[0], leach[1])
                response = requests.get(
                    url,
                    timeout=5,
                    verify=False,
                    headers=headers,
                    auth=auth,
                    allow_redirects=True,
                )

            if response.status_code == 404:
                logging.info(f"Missing {url}")
                return False

            response.raise_for_status()
            # Check the content type again
            content_type = response.headers.get("Content-Type", "").lower()
            # TODO: consider checking the content returned for the content headers
            # print(f"    updated content type {content_type} {url}")
        except Exception as e:
            if "unsupported" in str(e).lower():
                logging.info(f"Unsupported RANGE {url}: {e}")
            elif "method not allowed" in str(e).lower():
                logging.info(f"Not allowed RANGE {url}: {e}")
            elif "401 client error" in str(e).lower():
                logging.info(f"Error RANGE {url}: {e}")
            elif "timeout" in str(e).lower():
                logging.error(f"Error RANGE {url}: {e}")
            else:
                logging.warn(f"Error performing range request for {url}: {e}")
            # print(" warn2", response.headers)

    if (
        content_type != ""
        and last_camera_header_time.get(url, 0) < time.time() - 60 * 60
    ):
        # print("saved content type!", name, content_type,  last_camera_header_time.get(url,0), time.time() - 60*60)
        last_camera_header[url] = content_type
        last_camera_header_time[url] = time.time()

    # Check if the URL is an obvious image based on its extension, some hax
    if (
        any(
            ext in url.lower()
            for ext in [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".gif", "/picture"]
        )
        or "image/" in content_type
        and not danger
    ):
        # Attempt to download the image directly
        # print(" trying picture", url)
        image_saved = download_image(
            url, output_path, timeout=timeout, name=name, invert=invert
        )
        # print("   attempt", content_type, url, image_saved)
        if image_saved:
            # logging.info(f"Successfully downloaded image from {url}")
            # if content_type == '':
            #    print("   MISSING CONTENT TYPE1", url)
            if (
                "image/" not in content_type
                and last_camera_header_time.get(url, 0) < time.time() - 60 * 60
            ):
                last_camera_header[url] = "image/unknown"
                last_camera_header_time[url] = time.time()
                # print("* *** saved content type1!", name, content_type)
            return True
        logging.warn(
            f"Failed to download image directly from {url}, attempting to capture screenshot..."
        )

    if (
        any(ext in url.lower() for ext in [".pdf"])
        or "/pdf" in content_type
        and not danger
    ):
        image_saved = download_pdf(
            url, output_path, timeout=timeout, name=name, invert=invert
        )
        if image_saved:
            # if content_type == '':
            #    print("   MISSING CONTENT TYPE2", url)
            if (
                "/pdf" not in content_type
                and last_camera_header_time.get(url, 0) < time.time() - 60 * 60
            ):
                last_camera_header[url] = "application/pdf"
                last_camera_header_time[url] = time.time()
                # print("* *** saved content type2!", name, content_type)
            # logging.info(f"Successfully downloaded image from {url}")
            return True

    # Check for media stream URLs
    #  # port :5004 is an obvious homerunhd machine
    if (
        any(
            ext in url.lower()
            for ext in [".mjpg", ".mp4", ".gif", ".webp", "rtsp://", ".m3u8", ":5004/"]
        )
        or "video/" in content_type
        and not danger
    ):
        frame_captured = capture_frame_from_stream(
            url, output_path, timeout=timeout, name=name, invert=invert
        )
        if frame_captured:
            # if content_type == '':
            #    print(" MISSING CONTENT TYPE3", content_type, url)
            if (
                "video/" not in content_type
                and last_camera_header_time.get(url, 0) < time.time() - 60 * 60
            ):
                last_camera_header[url] = "video/unknown"
                last_camera_header_time[url] = time.time()
                # print("* *** saved content type3!", name, content_type)
            return True
    if (
        is_enhanced(url) and not danger
    ):  # Note - we probably dont want to do this if its like a home page or something.  can we parse and check?
        frame_captured = capture_frame_with_ytdlp(
            url, output_path, name=name, invert=invert
        )
        if frame_captured:
            return True

    # try with a very lightweight browser
    if (
        re.findall(r"^https?://", url, flags=re.I)
        and dedicated_selector in [None, ""]
        and popup_xpath in [None, ""]
        and headless is True
        and stealth is False
        and browser is False
        and not is_enhanced(url)
        and not danger
    ):
        image_saved = capture_screenshot_and_har_light(
            url,
            output_path,
            timeout,
            name=name,
            invert=invert,
            proxy=template.get("proxy"),
            dark=dark,
        )
        if image_saved:
            # if content_type == '':
            #    print(" MISSING CONTENT TYPE5", content_type, url)
            if (
                "text/" not in content_type
                and last_camera_header_time.get(url, 0) < time.time() - 60 * 60
            ):
                last_camera_header[url] = "text/html"
                last_camera_header_time[url] = time.time()
                # print("* *** saved content type5!", name, content_type)
            return True
        logging.warn(f"Failed to access via webkit {url}, attempting chrome...")

    # If direct download fails or URL is not an obvious image, capture screenshot
    if re.findall(r"^https?://", url, flags=re.I):
        # if we failed over to here, we're taking the browser
        if browser is False:
            headless = True

        image_saved = capture_screenshot_and_har(
            url,
            output_path,
            popup_xpath,
            dedicated_selector,
            timeout,
            name=name,
            invert=invert,
            proxy=template.get("proxy"),
            headless=headless,
            dark=dark,
            stealth=stealth,
            danger=danger,
        )
        if image_saved:
            # if content_type == '':
            #    print(" MISSING CONTENT TYPE6", content_type, url)
            if (
                "text/" not in content_type
                and last_camera_header_time.get(url, 0) < time.time() - 60 * 60
            ):
                last_camera_header[url] = "text/html"
                last_camera_header_time[url] = time.time()
                # print("* *** saved content type!", name, content_type)
            return True
        logging.error(f"Failed to access via chrome {url} , quitting")

    # print(" CONTENT:", content_type, '::', last_camera_header.get(url,0), url)

    return False


def capture_frame_with_ytdlp(url: str, output_path: str, name: str = "unknown", invert: bool = False) -> bool:
    """Use yt-dlp to get the video URL and ffmpeg to capture a single frame from the video stream."""

    if shutil.which("yt-dlp") is None:
        print("yt-dlp is not installed or not in the system path.")
        return False

    try:
        # Use yt-dlp to get the direct video URL
        output_path + ".%(ext)s"
        ytdlp_command = [
            "yt-dlp",
            "--get-url",
            "--format",
            "bestvideo",  # Adjust the format as needed
            url,
        ]
        result = subprocess.run(
            ytdlp_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        video_url = result.stdout.decode().strip()  # Get the actual video URL

        # Use ffmpeg to capture a frame from the video URL
        ffmpeg_command = [
            "ffmpeg",
            "-analyzeduration",
            "20M",
            "-probesize",
            "20M",
            "-ec",
            "15",
            "-i",
            video_url,  # Input stream URL from yt-dlp
            "-sn",
            "-an",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "rgb24",
            "-frames:v",
            "1",  # Capture only one frame
            #'-fflags', '+discardcorrupt',
            "-fflags",
            "+igndts+ignidx+genpts+fastseek+discardcorrupt",
            "-q:v",
            "0",  # Output quality (lower is better)
            #'-vf', 'fps=fps=1',
            "-f",
            "image2",  # Force image2 muxer
            "-y",
            output_path,  # Output file path
        ]
        subprocess.run(
            ffmpeg_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if os.path.exists(output_path):
            # if dark: # TODO
            #    image = apply_dark_mode(image)
            add_timestamp(output_path, name=name, invert=invert)
            # logging.info(f"Successfully captured frame from video stream {url}")
            return True
        logging.info(f"Unsuccessfully captured frame from video stream {url}")
    except Exception as e:
        logging.error(f"Error capturing frame with yt-dlp and ffmpeg: {e}")
    return False


def capture_frame_from_stream(
    url: str, output_path: str, num_frames: int = 3, timeout: int = 30, name: str = "unknown", invert: bool = False
) -> bool:
    """Use ffmpeg to capture multiple frames from a video stream and save the last one."""
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not installed or not in the system path.")
        return False

    with tempfile.TemporaryDirectory() as tmpdirname:  # todo make sure this gets dleted
        # Capture multiple frames into the temporary directory
        temp_output_pattern = os.path.join(tmpdirname, "frame_%03d.png")
        command = [
            "ffmpeg",
            "-hide_banner",
            #'-hwaccel', 'auto',
        ]

        probe_size = "5M"
        if "http:" in url or "https:" in url:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            command.extend(["-headers", "User-Agent: %s\r\n" % UA])
            command.extend(["-headers", f"referer: {base_url}\r\n"])
            command.extend(["-headers", f"origin: {base_url}\r\n"])
            command.extend(["-seekable", "0"])
            # command.extend(['-timeout', str(timeout-1)])  # not sure why, but this causes us a lot of issues, dont set a timetout
            probe_size = "5M"
        elif "rtsp:" in url:
            command.extend(["-rtsp_transport", "tcp"])
            probe_size = "10M"
            if "/streaming/" in url.lower():  # alittle bit of a hack
                command.extend(["-c:v", "h264"])
                command.extend(["-r", "1"])
                probe_size = "20M"
        else:
            probe_size = "20M"

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
                str(num_frames),  # Capture 'num_frames' frames
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
                    timeout=17,
                )  # wanring hardcoded
                # print("mmm", ' '.join(command))
                # subprocess.run(command, check=True, timeout=timeout) # wanring hardcoded
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

    logging.error(f"Error capturing frame with ffmpeg: {url}")
    return False


def add_options(options: Union[webdriver.ChromeOptions, Options], uc: bool = False) -> Union[webdriver.ChromeOptions, Options]:
    options.add_argument("--disabled")

    # https://stackoverflow.com/questions/62889739/selenium-gives-timed-out-receiving-message-from-renderer-for-all-websites-afte
    options.add_argument("--disable-infobars")

    options.add_argument("--disable-notifications")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--dns-prefetch-disable")
    options.add_argument("--disable-ip-pooling")
    options.add_argument("--disable-async-dns")
    options.add_argument("--disable-background-mode")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-bundled-ppapi-flash")
    options.add_argument("--disable-component-update")

    options.add_argument("--disable-crl-sets")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-dhcp-wpad")
    options.add_argument("--disable-ntp-other-sessions-menu")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-restore-session-state")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-preconnect")
    options.add_argument("--disable-web-sockets")
    options.add_argument("--disable-rasterization")

    # options.add_argument("--disable-web-security")  # instantly causes a lot of blocks for some reason?
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")

    options.add_argument("--allow-running-insecure-content")
    # options.add_argument("--disable-webgl") # needed for certain sites like flightradar
    options.add_argument("--disable-accelerated-2d-canvas")

    options.add_argument("--disable-webaudio")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.add_argument("--enable-logging")
    options.add_argument("--password-store=basic")

    options.add_argument("--start-maximized")
    options.add_argument("--enable-precise-memory-info")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-hang-monitor")

    options.add_argument(
        "--ignore-urlfetcher-cert-requests"
    )  # stop those ocsp crl requests
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--no-pings")
    options.add_argument("--incognito")  # run extensions in regular mode
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-sync-dictionary")
    options.add_argument("--disable-full-history-sync")
    options.add_argument("--force-color-profile=srgb")
    options.add_argument("--host-resolver-retry-attempts=0")
    options.add_argument("--dns-prefetch-disable")
    options.add_argument("--pagination")
    options.add_argument("--disable-browser-side-navigation")
    # options.add_argument("--simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT'")
    options.add_argument("--disable-features=NetworkService")

    # kind of easy to spot...
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins-discovery")
    options.add_argument("--disable-background-networking")
    options.add_argument("--bwsi")
    options.add_argument("--script-badges")
    # options.add_argument("--single-process") # might be a flag for automation detection

    # memory optimizations...
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-component-extensions-with-background-pages")
    options.add_argument("--disable-breakpad")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-features=TranslateUI")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-speech-api")
    options.add_argument("--disable-offer-upload-credit-cards")
    options.add_argument("--disable-smooth-scrolling")
    """
    # still working it
    options.add_argument("--disable-print-preview")
    options.add_argument("--disable-databases")
    options.add_argument("--disable-local-storage")
    options.add_argument("--disable-site-isolation-trials")
    options.add_argument("--disable-shared-workers")
    options.add_argument("--disable-preconnect")
    options.add_argument("--aggressive-cache-discard")
    #options.add_argument("--disable-cache")
    """
    options.add_argument("--disable-application-cache")
    options.add_argument("--disable-features=NetworkPrediction")
    options.add_argument("--disable-features=AutofillCreditCardParsing")
    options.add_argument("--disable-features=AutofillAddressNormalizer")
    options.add_argument("--disable-features=HeavyAdIntervention")
    options.add_argument("--disable-v8-idle-tasks")
    options.add_argument("--memory-pressure-off")
    options.add_argument("--disable-permissions-api")

    # options.add_argument("--disable-accelerated-video-decode")
    # options.add_argument("--disable-3d-apis")
    # --disable-webgl # maybe
    # --disable-webgl2 # maybe

    # TODO: make configurable
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--accept-lang=%s" % LANG)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-features=WebRtcHideLocalIpsWithMdns")

    # looks so bad without this lol
    # options.add_argument("--disable-remote-fonts")

    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    options.add_experimental_option(
        "perfLoggingPrefs", {"enableNetwork": True, "enablePage": False}
    )

    # options.add_argument("--enable-rtc")
    # doesn't work for some reason... cant parse
    # options.add_experimental_option('prefs', {'intl.accept_languages': 'en-US,en'})
    # prefs = {"download.default_directory" : "/dev/null", "download.prompt_for_download": False, "download.directory_upgrade": True, "safebrowsing.enabled": True }

    prefs = {
        "profile.default_content_setting_values.media_stream_mic": 1,
        "profile.default_content_setting_values.media_stream_camera": 1,
        "profile.default_content_setting_values.geolocation": 1,
        "profile.default_content_setting_values.notifications": 1,
        "profile.managed_default_content_settings.images": 1,
        "webrtc.ip_handling_policy": "default_public_interface_only",
        # "webrtc.ip_handling_policy": "disable_non_proxied_udp",
        "webrtc.multiple_routes_enabled": False,
        "webrtc.nonproxied_udp_enabled": False,
        "safebrowsing.enabled": True,
    }
    # print("PREFS", prefs)
    if uc is False:
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation", "enable-logging"]
        )  # To disable unwanted console logs # unfortunately not supported on UC
        options.add_experimental_option("useAutomationExtension", False)

    return options


def network_idle_condition(driver: webdriver.Chrome, url: str, timeout: int = 30, idle_time: float = 0.25, stealth: bool = False) -> Tuple[bool, int]:
    """
    Returns a function that can be used as a condition for WebDriverWait.
    It checks if the network has been idle for a specified amount of time.

    :param driver: The WebDriver instance.
    :param timeout: Maximum time to wait for the network to become idle.
    :param idle_time: Time in seconds that the network should be idle.
    """

    gurl = url.split("#")[0]
    lstatus = 800

    lsucc = False
    if True:
        time.time()
        end_time = time.time() + timeout
        not_moving = 0
        while time.time() < end_time:

            if not_moving > 5:
                break

            logs = driver.get_log("performance")
            events = [
                log
                for log in logs
                if "Network.response" in log["message"]
                or "Network.request" in log["message"]
            ]
            for gevent in events:
                levent = json.loads(gevent.get("message"))
                lurl = (
                    levent.get("message", {})
                    .get("params", {})
                    .get("response", {})
                    .get("url")
                )
                if lurl == gurl:
                    lstatus = (
                        levent.get("message", {})
                        .get("params", {})
                        .get("response", {})
                        .get("status")
                    )

                    if 400 <= lstatus <= 499:
                        # some kind of web server error
                        # print("WARNING STATUS:", lstatus, url)
                        logging.error(f"Webserver error for {url} {lstatus}")
                        return False, lstatus
                    else:
                        lsucc = True, lstatus
            if not events:
                not_moving += 1
            else:
                not_moving = 0
            time.sleep(idle_time)
    if lsucc is True:
        return True, lstatus

    if stealth is False:
        return True, lstatus
    logging.error(f"Webserver timeout {url}")
    # print("   timeout", url, stealth)

    return False, lstatus


def apply_dark_mode(img: Image.Image, range_value: int = 30, text_range_value: int = 120) -> Image.Image:
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


import shlex

def capture_screenshot_and_har_light(
    url: str, output_path: str, timeout: int = 30, name: str = "unknown", invert: bool = False, proxy: Optional[str] = None, dark: bool = True
) -> bool:
    """
    Capture a screenshot of a URL using wkhtmltoimage (WebKit).

    :param url: URL to capture.
    :param output_path: Name of the screenshot.
    """
    # Check if wkhtmltoimage is available
    if shutil.which("wkhtmltoimage") is None:
        print("wkhtmltoimage is not installed or not in the system path.")
        return False

    output_path = output_path.replace(".png", ".tmp.png")

    lsuccess = False

    ltime = time.time()

    # Prepare the command
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
    ]

    # Safely add the URL to the command
    command.append(shlex.quote(url))
    command.append(shlex.quote(output_path))

    # Execute the command
    try:
        result = subprocess.run(
            command, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False
        )
        result.stdout.decode("utf-8")
        result.stderr.decode("utf-8")
        # consider handling failures
        if result.returncode != 0:
            return False
    except Exception as e:
        if "timed out" not in str(e):
            print(" subprocess issue...", e)
        return False

    if os.path.exists(output_path):
        image = Image.open(output_path)
        try:
            image = image.convert("RGB")
        except Exception:
            print(" .. image exception")
            return False

        if is_mostly_blank(image):
            os.unlink(output_path)
            return False

        # Convert the image to RGBA mode in case it's a format that doesn't support transparency
        image = image.convert("RGB")
        image = remove_background(image)

        if dark:
            image = apply_dark_mode(image)
        image.save(output_path, "PNG")

        if os.path.exists(output_path):
            # TODO: add error mark from lerror
            add_timestamp(output_path, name, invert=invert)
            lsuccess = True
            os.rename(output_path, output_path.replace(".tmp.png", ".png"))
        else:
            os.unlink(output_path)
            lsuccess = False

    # Here you would also capture HAR data, but let's focus on the screenshot for simplicity
    # Mock HAR Data (for demonstration)
    # Normally, you would save or process HAR data here

    logging.info(
        f"Successfully captured light screenshot for {url} at {output_path} {round(time.time() - ltime,3)}"
    )

    return lsuccess


chrome_version = {}


def get_chrome_version(chrome_path: str) -> str:
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


def extract_version(driver_path: str) -> int:
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


def is_port_open(host: str, port: int, timeout: int = 5) -> bool:
    """Check if a network port is open on the specified host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False


def capture_screenshot_and_har(
    url: str,
    output_path: str,
    popup_xpath: Optional[str] = None,
    dedicated_selector: Optional[str] = None,
    timeout: int = 30,
    name: str = "unknown",
    invert: bool = False,
    proxy: Optional[str] = None,
    stealth: bool = False,
    dark: bool = True,
    headless: bool = True,
    danger: bool = False,
) -> bool:
    """
    Capture a screenshot of a URL using headless Chrome, optionally removing a popup before taking the screenshot.

    :param url: URL to capture.
    :param output_path: Name of the screenshot.
    :param popup_xpath: Optional XPath for a popup element to remove.
    """
    lsuccess = False
    ltime = time.time()

    # the chrome driver isnt open?  Quit right away and log
    if danger and not is_port_open("127.0.0.1", 9222):
        logging.warn("Danger port is not open - won't properly connect")
        return False

    # TODO: if danger, consider skipping this is the mouse has recently moved.

    # TODO: handle the use case of opening up a stream with the browser. We want it to cancel right away when that happens. I've noticed junk files get created in the root when this happens

    display = None
    driver = None
    chrome_service = None
    main_version = None
    current_window_handle = None
    new_window_handle = None
    try:
        if danger:
            # if headless: # try not to do this... user agent leaks and hard to unwind
            #    chrome_options.add_argument("--headless")
            # else:

            # display = Display(visible=0, size=(1920, 1080))
            # display.start()
            # os.environ['DISPLAY'] = ':' + str(display.display)
            # print(f"Virtual display started on :{display.display}")

            # Connect to the existing Chrome session
            options = webdriver.ChromeOptions()
            options.page_load_strategy = "none"
            # options = add_options(Options(), uc=True)
            options.binary_location = "/usr/bin/google-chrome"
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--new-window")

            user_data_dir = os.path.expanduser("~/.config/google-chrome")
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument("--profile-directory=Default")
            # if headless:
            #    options.add_argument(f'--headless')
            options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            options.set_capability(
                "goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"}
            )
            # options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
            # TODO: if danger mode, check if its already open and running
            driver = webdriver.Chrome(options=options)

            # TODO: should we consider a different display?()
        else:
            chrome_service = Service(ChromeDriverManager().install())
            driver_path = chrome_service.path
            main_version = extract_version(driver_path)

            # Note - if you're getting a lot of weird errors about the wrong chromedriver version, sometimes its best to
            #  clear your ~/.wdm cache.

            if stealth:
                options = webdriver.ChromeOptions()
                # options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
                # options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
                options.set_capability(
                    "goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"}
                )

                if headless:
                    driver = uc.Chrome(
                        version_main=main_version,
                        service=chrome_service,
                        use_subprocess=False,
                        headless=True,
                        options=options,
                    )
                else:
                    display = Display(visible=0, size=(1920, 1080))
                    display.start()
                    driver = uc.Chrome(
                        version_main=main_version,
                        service=chrome_service,
                        use_subprocess=False,
                        options=options,
                    )
            else:
                chrome_options = add_options(Options())
                if (
                    headless
                ):  # try not to do this... user agent leaks and hard to unwind
                    chrome_options.add_argument("--headless")
                else:
                    display = Display(visible=0, size=(1920, 1080))
                    display.start()
                chrome_options.add_argument("--user-agent=%s" % UA)
                driver = webdriver.Chrome(
                    service=chrome_service, options=chrome_options
                )

        if danger:

            # TODO: test if the system is idle

            current_window_handle = driver.current_window_handle
            try:
                # now, test if the browser is idle
                script = """(function(){let l=Date.now();['mousemove','keydown','scroll','click'].forEach(e=>document.addEventListener(e,()=>l=Date.now()));window.getIdleTime=()=>Date.now()-l;})();"""
                lret1 = driver.execute_script(script)
                #  if there is activity, skip on this.  Don't mess up the computer for a screenshot (only when idle)
                time.sleep(10)
                lret = driver.execute_script("return window.getIdleTime();")
                print("LRET", lret1, lret)
                if lret < 10000:
                    print(" activity...")
                    logging.warn("activity detected")
                    return False
                # tmp_window_handle = driver.current_window_handle
                # driver.switch_to.window(tmp_window_handle)
                # driver.switch_to.window(current_window_handle)
                # time.sleep(1)
            except Exception as e:
                print("> dupe timeout warning", e)

            current_window_handle = driver.current_window_handle
            driver.execute_script("window.open('', '_blank');")
            driver.switch_to.window(driver.window_handles[-1])
            new_window_handle = driver.current_window_handle
            if (
                new_window_handle is None or new_window_handle == current_window_handle
            ):  # failed to open a new handle, I think
                # finally() probably going to trip this up..
                driver.switch_to.window(current_window_handle)
                logging.warn("duplicate session")
                return False

        if not danger:
            driver.set_window_size(1920, 1080)
            driver.execute_cdp_cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1920,
                    "height": 1080,
                    "mobile": False,
                    "deviceScaleFactor": 1,
                },
            )
            driver.execute_script(
                "window.screen.width = 1920; window.screen.height = 1080;"
            )
            driver.execute_script(
                "window.innerWidth = 1920; window.innerHeight = 1080;"
            )

        if not invert and dark:
            driver.execute_cdp_cmd(
                "Emulation.setAutoDarkModeOverride", {"enabled": True}
            )

        if not danger:
            driver.delete_all_cookies()

        driver.set_page_load_timeout(timeout)
        gtime = time.time()
        driver.get(url)

        # TODO: switch back to the main context.
        if danger and current_window_handle:
            # note, might not exist...
            driver.switch_to.window(current_window_handle)

        lret, lstatus = network_idle_condition(driver, url, timeout, stealth)
        if not lret:
            if not stealth:
                max(timeout - (time.time() - ltime), 15)
                logging.warn(
                    f"Vanilla non-idle connection detected {url} at {output_path}, failing over to undetectable chromedriver"
                )
                """
                if danger:
                    try:
                        driver.switch_to.window(new_window_handle)
                        if driver:
                            driver.close()
                    except Exception as e:
                        pass
                    try:
                        driver.switch_to.window(current_window_handle)
                    except Exception as e:
                        pass
                if driver and not danger:
                    driver.quit()
                if display:
                    display.stop()
                # TODO: cap attempts....
                print("RETRY!!!!")
                return capture_screenshot_and_har(url, output_path, popup_xpath, dedicated_selector, timeout, name, invert, proxy, stealth=True, headless=headless, danger=danger)
                """
                return False  # dont stress on this for now

            if int(lstatus) >= 400:

                """
                if danger:
                    try:
                        driver.switch_to.window(new_window_handle)
                        if driver:
                            driver.close()
                    except Exception as e:
                        pass
                    try:
                        driver.switch_to.window(current_window_handle)
                    except Exception as e:
                        pass
                if driver and not danger:
                    driver.quit()
                if display:
                    display.stop()
                """
                return False

        if danger and time.time() - gtime < 10:
            time.sleep(10 - (time.time() - gtime))
        elif time.time() - gtime < 5:
            time.sleep(5 - (time.time() - gtime))

        if popup_xpath:
            try:
                elements = driver.find_elements(By.XPATH, popup_xpath)
                for element in elements:
                    driver.execute_script(
                        """var element = arguments[0]; element.parentNode.removeChild(element); """,
                        element,
                    )
            except Exception:
                pass

        #####  screenshot
        if danger:
            current_window_handle = driver.current_window_handle
            driver.switch_to.window(new_window_handle)

        if dedicated_selector:
            try:
                element = driver.find_element(By.XPATH, dedicated_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)

                if "//iframe" in dedicated_selector:
                    driver.switch_to.frame(element)
                    try:
                        element = driver.find_element(By.XPATH, "//video")
                        element.screenshot(output_path)
                    except Exception:
                        driver.save_screenshot(output_path)

                if not os.path.exists(output_path):
                    element.screenshot(output_path)
            except Exception:
                chrome_service = Service(ChromeDriverManager().install())

        if not os.path.exists(output_path):
            driver.save_screenshot(output_path)

        #####  screenshot
        if danger:
            driver.close()  # close the newly opened tab so we dont have to do it again later
            new_window_handle = None
            driver.switch_to.window(current_window_handle)

        if os.path.exists(output_path):
            image = Image.open(output_path)
            image = image.convert("RGB")
            image = remove_background(image)
            image.save(output_path, "PNG")
            if os.path.exists(output_path):
                add_timestamp(output_path, name, invert=invert)

        logging.info(f"Successfully captured screenshot for {url} at {output_path}")
        lsuccess = True
    except TimeoutException:
        logging.warn(f"Timed out waiting for network to be idle for {url}")
    except Exception as e:
        print(f"Error capturing screenshot for {url}", e, main_version)
        logging.error(
            f"Error capturing screenshot for {url}: {e} stealth: %s headless: %s"
            % (stealth, headless)
        )
        """
        chrome_service = Service(ChromeDriverManager().install())

        if not stealth:
            ltimeout = max(timeout - (time.time() - ltime), 15)
            logging.warn(f"Vanilla generic error detected {url} at {output_path}, failing over to undetectable chromedriver")
            if danger:
                driver.switch_to.window(new_window_handle)
                if driver:
                    driver.close()
                driver.switch_to.window(current_window_handle)
            if driver and not danger:
                driver.quit()
            if display:
                display.stop()
            return capture_screenshot_and_har(url, output_path, popup_xpath, dedicated_selector, timeout, name, invert, proxy, stealth=True, danger=danger)
        """
    finally:
        if danger:
            if new_window_handle:
                try:
                    driver.switch_to.window(
                        new_window_handle
                    )  # this should always fail.. there shouldnt be a new_window_handle
                    if driver and current_window_handle != new_window_handle:
                        driver.close()
                except Exception as e:
                    print(">>>1", e)
                    pass

            if current_window_handle:
                try:
                    driver.switch_to.window(current_window_handle)
                except Exception as e:
                    print(">>>2", e)
                    pass
        if driver and not danger:
            driver.quit()
        if display:
            display.stop()

        # Clean up temporary Chrome files
        try:
            temp_chrome_dirs = glob.glob('/tmp/.com.google.Chrome.*')
            current_time = time.time()
            cleaned_dirs = 0
            for temp_dir in temp_chrome_dirs:
                # Check if the directory hasn't been modified in the last hour
                if current_time - os.path.getmtime(temp_dir) > 3600:  # 3600 seconds = 1 hour
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    cleaned_dirs += 1
            logging.info(f"Cleaned up {cleaned_dirs} temporary Chrome directories")
        except Exception as e:
            logging.error(f"Error cleaning up temporary Chrome files: {e}")

    return lsuccess
