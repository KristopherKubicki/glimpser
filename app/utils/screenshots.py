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
import time
from urllib.parse import urlparse
import glob
import base64
import nodriver
import psutil
from werkzeug.utils import secure_filename
import urllib3
from dateutil import tz
import random

os.environ["WDM_LOG"] = "0"
os.environ["WDM_LOG_LEVEL"] = "0"
logging.getLogger("webdriver_manager").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.ERROR)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import numpy as np
import requests
import yt_dlp as youtube_dl
from pdf2image import convert_from_path
from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageOps,
    ImageStat,
)
import textwrap
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

try:
    from pynput import mouse, keyboard
except Exception as e:  # pragma: no cover - optional dependency
    mouse = None
    keyboard = None
    logging.warning("pynput not available: %s", e)


from app.config import (
    DEBUG,
    LANG,
    SCREENSHOT_DIRECTORY,
    UA,
    FFMPEG_PATH,
    FFMPEG_HWACCEL,
    NUM_FRAMES,
    CAPTURE_TIMEOUT,
    PROBE_SIZE_DEFAULT,
    PROBE_SIZE_RTSP,
    PROBE_SIZE_OTHER,
    ANALYZE_DURATION_DEFAULT,
    ANALYZE_DURATION_RTSP,
    ANALYZE_DURATION_OTHER,
    TZ,
)
import app.config as config
from app.utils.validators import validate_proxy, validate_url

last_camera_test = {}
last_camera_test_time = {}
last_camera_header = {}
last_camera_header_time = {}
last_camera_light = {}
last_camera_light_time = {}
lurl_cache = {}
lurl_cache_time = {}
throttle_cache = {}
chrome_version = {}
last_modified_cache = {}
etag_cache = {}

# Cache of last HTTP status codes per URL
status_code_cache = {}
status_code_cache_time = {}
STATUS_CACHE_TTL = 60 * 60  # 1 hour
STATUS_CACHE_PATH = "data/status_cache.json"


def _load_status_cache() -> None:
    """Load cached status codes from ``STATUS_CACHE_PATH``."""
    if not os.path.exists(STATUS_CACHE_PATH):
        return
    try:
        with open(STATUS_CACHE_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return

    status_code_cache.clear()
    status_code_cache_time.clear()
    for url, info in data.items():
        status_code_cache[url] = info.get("code")
        status_code_cache_time[url] = info.get("time", 0)


def _persist_status_cache() -> None:
    """Write ``status_code_cache`` to ``STATUS_CACHE_PATH``."""
    os.makedirs(os.path.dirname(STATUS_CACHE_PATH), exist_ok=True)
    data = {
        url: {"code": code, "time": status_code_cache_time.get(url, 0)}
        for url, code in status_code_cache.items()
    }
    try:
        with open(STATUS_CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        logging.exception("Failed to persist status cache")


_load_status_cache()


FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "LiberationSans-Regular.ttf",
]

# User agent templates used when stealth mode is enabled. The actual version is
# filled dynamically based on the installed Chrome version so that outdated
# strings are avoided.
STEALTH_UA_TEMPLATES = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 "
        "Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 "
        "Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 "
        "Safari/537.36"
    ),
]


def random_user_agent():
    """Return a randomized user agent string for stealth mode."""
    chrome_path = get_chrome_path()
    version = get_chrome_version(chrome_path)
    # Pick a nearby version to avoid obvious automation patterns
    major_version = random.randint(max(100, version - 1), version + 1)
    template = random.choice(STEALTH_UA_TEMPLATES)
    return template.format(version=major_version)


def load_font(size):
    """Return a truetype font for overlays."""
    for font_name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_name, size)
        except IOError:
            continue
    return ImageFont.load_default()


# Global flag to track user activity
user_active = False

_DRIVER = None


def get_driver(opts):
    global _DRIVER
    if _DRIVER is None:
        service = Service(ChromeDriverManager().install())
        _DRIVER = webdriver.Chrome(service=service, options=opts)
    return _DRIVER


_session = None


def http_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.verify = False
        _session.headers.update({"user-agent": UA})
        _session.headers.update({"Accept": "*/*"})
        _session.mount("http://", requests.adapters.HTTPAdapter(pool_maxsize=20))
        _session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=20))
    return _session


def _is_valid_png(path):
    try:
        with Image.open(path) as im:
            im.verify()  # raises if corrupt/zero-byte
        return True
    except Exception:
        return False


def get_cached_status_code(url):
    """Return cached HTTP status code for URL if not expired."""
    code = status_code_cache.get(url)
    ts = status_code_cache_time.get(url, 0)
    if code is not None and time.time() - ts < STATUS_CACHE_TTL:
        return code
    if code is not None:
        # Entry expired, remove and persist cleanup
        status_code_cache.pop(url, None)
        status_code_cache_time.pop(url, None)
        _persist_status_cache()
    return None


def set_cached_status_code(url, code):
    """Store status code for URL with current timestamp."""
    status_code_cache[url] = code
    status_code_cache_time[url] = time.time()
    _persist_status_cache()


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


import ctypes, ctypes.util, os, time


class XScreenSaverInfo(ctypes.Structure):
    _fields_ = [
        ("window", ctypes.c_ulong),
        ("state", ctypes.c_int),
        ("kind", ctypes.c_int),
        ("since", ctypes.c_ulong),  # ms since state started
        ("idle", ctypes.c_ulong),  # ms idle (what we need)
        ("eventMask", ctypes.c_ulong),
    ]


def idle_seconds_x11() -> int:
    """
    Seconds since last keyboard/mouse event in *this* X display.

    Raises RuntimeError instead of segfaulting if:
      * DISPLAY is unset,
      * libXss is missing,
      * XScreenSaver extension is not present/enabled.
    """
    dpy_name = os.environ.get("DISPLAY")
    if not dpy_name:
        raise RuntimeError("$DISPLAY is not set – not running under X11.")

    # ----------- open libraries ------------------------------------------------
    libX11_path = ctypes.util.find_library("X11")
    libXss_path = ctypes.util.find_library("Xss")  # screensaver ext.
    if not (libX11_path and libXss_path):
        raise RuntimeError("libX11 or libXss not found (install libx11-6 libxss1).")

    x11 = ctypes.cdll.LoadLibrary(libX11_path)
    xss = ctypes.cdll.LoadLibrary(libXss_path)

    # ----------- declare signatures (prevents segfaults) -----------------------
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p

    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong

    xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)

    xss.XScreenSaverQueryInfo.argtypes = [
        ctypes.c_void_p,  # Display*
        ctypes.c_ulong,  # Drawable (root win)
        ctypes.POINTER(XScreenSaverInfo),  # info struct
    ]
    xss.XScreenSaverQueryInfo.restype = ctypes.c_int  # Status (non-zero = OK)

    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XFree.restype = None
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = None

    # ----------- do the work ---------------------------------------------------
    dpy = x11.XOpenDisplay(dpy_name.encode())
    if not dpy:
        raise RuntimeError(f"cannot open X display '{dpy_name}'")

    info = xss.XScreenSaverAllocInfo()
    if not info:
        x11.XCloseDisplay(dpy)
        raise RuntimeError("XScreenSaverAllocInfo returned NULL")

    root = x11.XDefaultRootWindow(dpy)
    status = xss.XScreenSaverQueryInfo(dpy, root, info)
    if status == 0:
        x11.XFree(info)
        x11.XCloseDisplay(dpy)
        raise RuntimeError("XScreenSaver extension not active on this X server")

    idle_ms = info.contents.idle
    x11.XFree(info)
    x11.XCloseDisplay(dpy)
    return idle_ms // 1000  # convert to whole seconds


def idle_seconds_loginctl() -> int:
    """Return seconds of user idleness according to systemd-logind.
    0  → actively using keyboard/mouse right now."""
    import os, subprocess, time

    uid = os.getuid()
    try:
        out = subprocess.check_output(
            [
                "loginctl",
                "show-user",
                str(uid),
                "-p",
                "IdleHint",
                "-p",
                "IdleSinceHintMonotonicUSec",
            ],
            text=True,
            timeout=0.3,  # fail fast
        ).splitlines()
    except subprocess.SubprocessError:
        raise RuntimeError("loginctl unavailable")

    props = dict(l.split("=", 1) for l in out if "=" in l)
    if props.get("IdleHint", "no") != "yes":
        return 0  # user is active

    idle_us = int(props["IdleSinceHintMonotonicUSec"])
    return int((time.monotonic() * 1_000_000 - idle_us) / 1_000_000)


# Function to detect user activity
def check_user_activity(timeout=10):

    global user_active
    user_active = False

    # oiq = make_idle_irq()
    # liq = oiq()
    # if liq < 120:
    #    user_active = True  # allow to check on listeners for the 0 second case
    #    return user_active
    try:
        idle_seconds_x = idle_seconds_x11()
        if idle_seconds_x < 120:
            user_active = True  # user recently active
            return user_active
    except Exception as e:
        logging.debug(f"idle_seconds_x11 failed: {e}")

    # idle_seconds = idle_seconds_loginctl()
    # if 1 < idle_seconds < 120:
    #    user_active = True  # allow to check on listeners for the 0 second case
    #    return user_active

    if mouse is None or keyboard is None:
        return user_active

    # Create listeners for keyboard and mouse
    mouse_listener = mouse.Listener(
        on_move=on_move, on_click=on_click, on_scroll=on_scroll
    )
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

    # Ensure threads close their X connections before returning
    mouse_listener.join()
    keyboard_listener.join()

    return user_active


def _send_input_event():
    """Move the mouse slightly to generate an input event."""
    if mouse is None:
        return
    try:
        controller = mouse.Controller()
        x, y = controller.position
        controller.move(1, 0)
        controller.move(-1, 0)
        controller.position = (x, y)
    except Exception as e:  # pragma: no cover - best effort
        logging.debug(f"_send_input_event failed: {e}")


def detect_background_color(image: Image.Image, sample_width: int = 10):
    """Return the most common color found along the image border."""
    arr = np.asarray(image.convert("RGBA"))
    top = arr[:sample_width, :, :].reshape(-1, 4)
    bottom = arr[-sample_width:, :, :].reshape(-1, 4)
    left = arr[:, :sample_width, :].reshape(-1, 4)
    right = arr[:, -sample_width:, :].reshape(-1, 4)
    border = np.concatenate([top, bottom, left, right], axis=0)
    colors, counts = np.unique(border, axis=0, return_counts=True)
    return tuple(int(c) for c in colors[counts.argmax()])


def remove_background(image, background_color=None, threshold=10):
    """Crop the image to remove the background color border and ensure a 16:9 aspect ratio."""
    if background_color is None:
        background_color = detect_background_color(image)
    # Find the bounding box of the non-background area
    bbox = find_bounding_box(image, background_color, threshold)

    # Adjust the bounding box to fit a 16:9 aspect ratio
    if bbox:
        bbox = adjust_bbox_to_aspect_ratio(bbox, image.size, aspect_ratio=(16, 9))
        image = image.crop(bbox)
    return image


def find_bounding_box(
    image: Image.Image,
    background_color=(14, 14, 14, 255),
    threshold: int = 10,
):
    """
    Return (left, top, right, bottom) that contains all pixels whose
    per-channel distance from `background_color` > threshold.

    If *every* pixel is background, returns None.
    """
    # RGBA → ndarray(H, W, 4)
    arr = np.asarray(image.convert("RGBA"), dtype=np.int16)

    bg = np.array(background_color, dtype=np.int16)
    # True where *any* channel differs more than threshold
    fg_mask = np.any(np.abs(arr - bg) > threshold, axis=-1)

    if not fg_mask.any():  # all background
        return None

    ys, xs = np.nonzero(fg_mask)
    top, bottom = ys.min(), ys.max()
    left, right = xs.min(), xs.max()

    return int(left), int(top), int(right), int(bottom)


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


def is_mostly_blank(
    image: Image.Image,
    threshold: float = 0.92,
    blank_color=(255, 255, 255),
    text_std_threshold: int = 20,
    dark_threshold: int = 10,
):
    """
    True  → we consider the frame “uninteresting” (blank / flat / too dark).
    False → keep the frame.
    """
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)

    # ---------- 1.  “Mostly blank?”  ----------
    blank = np.array(blank_color, dtype=np.int16)
    blank_px = np.all(np.abs(arr - blank) <= 30, axis=-1).mean()
    if blank_px >= threshold:
        return True

    # ---------- 2.  “Flat image?”  ----------
    # Low global std-dev ≈ little structure / shapes
    if arr.std() < text_std_threshold:
        return True

    # ---------- 3.  “Too dark?”  ----------
    # Use perceptual luma so pure-dark blue isn’t mis-treated
    luma = np.dot(arr.mean(axis=(0, 1)), [0.2126, 0.7152, 0.0722])
    if luma < dark_threshold:
        return True

    return False


def run_cmd(cmd, timeout):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()  # SIGKILL
        out, err = proc.communicate()
        raise RuntimeError(f"timeout: {' '.join(cmd)}")
    if proc.returncode:
        raise RuntimeError(err.decode()[:300])
    return out


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

            draw = ImageDraw.Draw(image)
            # If the image has the "invert" flag, then invert colors for readability
            if invert:
                image = ImageOps.invert(image)

            # Define the timestamp format

            zone = tz.gettz(TZ) or tz.UTC  # fall back if the name is invalid
            local_time = datetime.datetime.now(zone)
            tz_name = local_time.tzname() or ""
            timestamp = local_time.strftime("%Y-%m-%d %H:%M:%S")
            if tz_name:
                timestamp = f"{timestamp} {tz_name}"

            utc_time = datetime.datetime.utcnow()
            utc_timestamp = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")

            max_height = min(image.height, image.width * 9 // 16)
            font_size = int(max_height * 0.05)
            if font_size < 5:  # ignore tiny images
                return

            top_offset = (image.height - max_height) / 2

            # Use the helper to load fonts. The small font is half-sized.
            font = load_font(font_size)
            font_small = load_font(int(max(5, font_size / 2)))

            padding = 6

            # Render the name in the upper-left corner
            x = padding
            y = int(padding + top_offset)
            bbox = draw.textbbox((x, y), name, font=font, stroke_width=1)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            background = Image.new(
                "RGBA",
                (text_w + padding * 2, text_h + padding * 2),
                (0, 0, 0, 128),
            )
            image.paste(background, (x - padding, y - padding), background)
            draw.text(
                (x, y),
                name,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
            )

            # Timestamp in the lower-right corner
            text_w = draw.textbbox((0, 0), timestamp, font=font, stroke_width=1)[2]
            x = image.width - text_w - padding
            y = int(image.height - top_offset - font_size * 2)
            bbox = draw.textbbox((x, y), timestamp, font=font, stroke_width=1)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            background = Image.new(
                "RGBA",
                (text_w + padding * 2, text_h + padding * 2),
                (0, 0, 0, 128),
            )
            image.paste(background, (bbox[0] - padding, bbox[1] - padding), background)

            draw.text(
                (x, y),
                timestamp,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
            )

            if utc_timestamp != timestamp:
                tz_bbox = draw.textbbox(
                    (0, 0), utc_timestamp + "Z", font=font_small, stroke_width=1
                )
                text_w = tz_bbox[2] - tz_bbox[0]
                text_h = tz_bbox[3] - tz_bbox[1]
                background = Image.new(
                    "RGBA",
                    (text_w + padding * 2, text_h + padding * 2),
                    (0, 0, 0, 128),
                )
                tz_x = x
                tz_y = y + font_size + padding
                image.paste(
                    background,
                    (tz_x - padding, tz_y - padding),
                    background,
                )
                draw.text(
                    (tz_x, tz_y),
                    utc_timestamp + "Z",
                    font=font_small,
                    fill=(255, 255, 255, 255),
                    stroke_width=1,
                    stroke_fill=(0, 0, 0, 255),
                )

            # Save the image
            image.save(image_path, "PNG")

        try:
            from .qrcode_overlay import add_micro_qr

            add_micro_qr(image_path, name)
        except Exception as e:  # pragma: no cover - overlay failures are non-critical
            logging.debug(f"Micro QR overlay failed: {e}")


def download_image(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    dark=False,
    stealth=False,
    proxy=None,
    username=None,
    password=None,
):
    """Attempt to download an image directly from the URL and convert it to PNG format.

    Args:
        url (str): Image URL.
        output_path (str): Where to save the PNG.
        timeout (int): Timeout in seconds.
        name (str): Friendly name for logging.
        invert (bool): If True, invert timestamp colors.
        dark (bool): Apply dark mode.
        stealth (bool): Use stealth user agent.
        proxy (str, optional): Proxy to use for the HTTP request.
    """

    proxy = validate_proxy(proxy)

    # ideally the timeout should be pretty high, its an image, and it could be real big
    if timeout < 10:
        timeout = 10

    response = None

    cached = get_cached_status_code(url)
    if cached is not None and cached != 200:
        logging.debug(f"Skipping {url} due to cached status {cached}")
        return False
    try:
        lua = UA
        if stealth:
            lua = random_user_agent()
        headers = {"user-agent": lua}
        proxies = {"http": proxy, "https": proxy} if proxy else None

        auth = get_auth(url, username, password)

        request_kwargs = dict(
            stream=True,
            timeout=(timeout, timeout * 3),
            verify=False,
            headers=headers,
            auth=auth,
        )
        if proxies:
            request_kwargs["proxies"] = proxies

        response = http_session().get(url, **request_kwargs)
        if response.status_code == 401 and auth is not None:
            auth = get_digest_auth(url, username, password)
            request_kwargs = dict(
                stream=True,
                timeout=(timeout, timeout * 3),
                verify=False,
                headers=headers,
                auth=auth,
            )
            if proxies:
                request_kwargs["proxies"] = proxies

            response = http_session().get(url, **request_kwargs)

        status = response.status_code
        set_cached_status_code(url, status)

        if status == 200:
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
            if os.path.exists(output_path) and _is_valid_png(output_path):
                add_timestamp(output_path, name=name, invert=invert)
                return True
        else:
            response.close()
            logging.warning(f"Error downloading image: HTTP status code {status} {url}")
    except Exception as e:
        logging.error(f"Error downloading image: {e} {url} {timeout}")
        set_cached_status_code(url, 0)
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
    dark=False,
    stealth=False,
    username=None,
    password=None,
):
    """
    Attempt to download the first page of a PDF from the URL and convert it to PNG format.
    """
    tmp_name = None  # path of the downloaded PDF
    lsuccess = False

    cached = get_cached_status_code(url)
    if cached is not None and cached != 200:
        logging.debug(f"Skipping PDF download for {url} due to cached status {cached}")
        return False

    if timeout < 10:
        timeout = 10

    try:
        # Download the PDF file
        lua = UA
        if stealth:
            lua = random_user_agent()

        headers = {"user-agent": lua}
        auth = get_auth(url, username, password)

        response = http_session().get(
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
            auth = get_digest_auth(url, username, password)
            response = http_session().get(
                url,
                stream=True,
                timeout=timeout,
                verify=False,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )
        set_cached_status_code(url, response.status_code)

        if response.status_code != 200:
            logging.error(f"Error downloading PDF: HTTP {response.status_code}")
            return False

        # Save PDF to a temp file

        tmpdirname = f"/tmp/glimpser_{name}"
        os.makedirs(tmpdirname, exist_ok=True)
        if os.path.exists(tmpdirname):
            with open(os.path.join(tmpdirname, "file.pdf"), "wb") as tmp:
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

        if os.path.exists(output_path) and _is_valid_png(output_path):
            add_timestamp(output_path, name=name, invert=invert)
            logging.debug(f"Successfully saved PDF page to {output_path}")
            lsuccess = True
        return lsuccess

    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        set_cached_status_code(url, 0)
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
    try:
        return subprocess.check_output(
            command, stderr=subprocess.STDOUT, timeout=timeout
        )
    except FileNotFoundError:
        return b""


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
        if address in ("google.com", "www.google.com"):
            return True
        return False

    # check the arp table, particularly if its an unroutable ip address
    if is_private_ip(ip_address):
        try:
            arp_entry = get_arp_output(ip_address, timeout).lower()
            if "no entry" in arp_entry.decode().lower():
                logging.warning("failing arp entry for %s", ip_address)
                return False
        except Exception as e:
            logging.warning("failure to arp %s", e)

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
        if address in ("google.com", "www.google.com"):
            return True
        return False
    except Exception as e:
        logging.warning(f"Socket error: {e}")
        if address in ("google.com", "www.google.com"):
            return True

    return False


def parse_url(url):
    """Return the domain and port extracted from *url*.

    ``urllib.parse.urlparse`` treats strings without a scheme oddly.  For
    example ``"example.com:8080/path"`` is parsed with ``"example.com"`` as the
    *scheme* rather than the hostname.  To handle such URLs we prefix ``"//"`` so
    they are interpreted as network locations.
    """

    # Handle URLs missing a scheme like ``example.com:8080/path`` by prefixing
    # ``//`` which causes ``urlparse`` to parse the hostname and port correctly.
    if "://" not in url:
        parsed_url = urlparse("//" + url)
    else:
        parsed_url = urlparse(url)

    domain = parsed_url.hostname
    if parsed_url.scheme == "" and domain is None:
        domain = re.sub(r"\/.+?$", "", parsed_url.path)

    port = parsed_url.port
    # If the port is None and the scheme is specified, infer the default port.
    if port is None:
        if parsed_url.scheme == "http":
            port = 80
        elif parsed_url.scheme == "https":
            port = 443
        # Add more schemes and their default ports if necessary.

    return domain, port


def cas_error(url):

    entry = throttle_cache.setdefault(url, {"errors": 0, "first": time.time()})

    if entry.get("last", 0) > time.time() - 60 * 5:
        entry["errors"] += 1
    else:
        entry["errors"] = 1
        entry["first"] = time.time()
    entry["last"] = time.time()

    if entry["errors"] > 2:
        logging.error(f"Could not reach host: {url} {entry['errors']} times")
        entry["timeout"] = time.time() + 60 * 60  # 1 hour timeout


def capture_or_download(name: str, template: dict) -> bool:
    """
    Decides whether to download the image directly or capture a screenshot based on the given template.

    This function is the main entry point for capturing or downloading content from a URL. It handles
    various types of content (images, PDFs, video streams, web pages) and uses different methods to
    obtain the content based on the URL and content type.

    Args:
        name (str): The name to be used for the output file.
        template (dict): A dictionary containing configuration parameters for the capture/download.

    Returns:
        bool: True if the capture/download was successful, False otherwise.
    """
    if name is None or template is None:
        return False

    # Extract parameters from the template
    url = template.get("url")
    username = template.get("auth_username")
    password = template.get("auth_password")

    # Disallow local file paths to avoid unintended file disclosure
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {"http", "https", "rtsp", "rtmp"}:
        logging.error("Unsupported URL scheme: %s", parsed.scheme)
        return False
    if throttle_cache.get(url) and throttle_cache[url].get("timeout", 0) > time.time():
        # just skip things that are obviously broken.  "Backoff"..
        return False
    if (
        lurl_cache.get(url, "none") != "good"
        and time.time() - lurl_cache_time.get(url, 0) < 3600
    ):  # try every 1 hour no matter what??
        return False

    cached_status = get_cached_status_code(url)
    if cached_status is not None and cached_status >= 400:
        logging.debug(f"Skipping {url} due to cached status {cached_status}")
        return False

    popup_xpath = template.get("popup_xpath")
    dedicated_selector = template.get("dedicated_xpath")
    timeout = int(template.get("timeout", 30) or 30)
    tstart = time.time()

    # Set flags based on template parameters
    invert = template.get("invert", "") not in ["", "false", False]
    headless = template.get("headless", "") not in ["", "false", False]
    dark = template.get("dark", "") not in ["", "false", False]
    stealth = template.get("stealth", "") not in ["", "false", False]
    browser = template.get("browser", "") not in ["", "false", False]
    danger = template.get("danger", "") not in ["", "false", False]

    if danger:
        browser = True
        headless = True

    # Check if the host is reachable for network URLs
    domain, port = parse_url(url)

    if domain:
        lreach = is_address_reachable(domain, port=port)
        if lreach is False:
            logging.debug(f"Could not reach host: {name} {url}")
            cas_error(url)
            return False

    # Prepare output path
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    output_path = os.path.join(SCREENSHOT_DIRECTORY, f"{name}/{name}_{timestamp}.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Determine content type
    content_type, is_modified = get_content_type(
        url, danger, stealth=stealth, username=username, password=password
    )

    # check if modified.
    if is_modified is False and not danger and not browser:
        cas_error(url)
        return True  # content has not changed...

    # Attempt to download or capture based on content type and URL
    if is_image_url(url, content_type) and not danger and not browser:
        lsuc = download_image(
            url,
            output_path,
            timeout,
            name,
            invert,
            dark,
            stealth,
            template.get("proxy"),
            username,
            password,
        )
        if lsuc is True:
            return lsuc
        cas_error(url)

    if is_pdf_url(url, content_type) and not danger and not browser:
        lsuc = download_pdf(
            url, output_path, timeout, name, invert, dark, stealth, username, password
        )
        if lsuc is True:
            return lsuc
        cas_error(url)

    if is_video_stream_url(url, content_type) and not danger and not browser:
        lsuc = capture_frame_from_stream(url, output_path, timeout, name, invert)
        if lsuc is True:
            return lsuc
        cas_error(url)

    if (
        is_enhanced(url) and not danger and not browser
    ):  # this is going to launch ytdlp, which is not a browser
        lsuc = capture_frame_with_ytdlp(url, output_path, name, invert)
        if lsuc is True:
            return lsuc
        cas_error(url)

    # Attempt lightweight browser capture for simple web pages, wont pick if theres xpath or anything
    if should_use_lightweight_browser(
        url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
    ):
        lsuc = capture_screenshot_and_har_light(
            url, output_path, timeout, name, invert, template.get("proxy"), dark
        )
        if lsuc is True:
            return lsuc
        if time.time() - tstart > timeout:
            logging.error(
                f"   *fail lightweight {url}"
            )  # if  we get a bunch of failures in a row here, we should block on lightweight
            cas_error(url)

    if should_use_phantom_browser(
        url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
    ):
        lsuc = capture_screenshot_phantom(
            url=url,
            output_path=output_path,
            timeout=timeout,
            name=name,
            dedicated_selector=dedicated_selector,
            invert=invert,
            dark=dark,
        )
        if lsuc is True:
            return lsuc
        if time.time() - tstart > timeout:
            logging.error(f"   *fail phantom {url} ")
            cas_error(url)

    # Fall back to full browser capture
    if re.findall(r"^https?://", url, flags=re.I):
        lsuc = capture_screenshot_and_har(
            url=url,
            output_path=output_path,
            popup_xpath=popup_xpath,
            dedicated_selector=dedicated_selector,
            timeout=timeout,
            name=name,
            invert=invert,
            proxy=template.get("proxy"),
            dark=dark,
            stealth=stealth,
            danger=danger,
        )
        if lsuc is True:
            return lsuc

        if not danger:
            cas_error(url)

    if not danger:
        # logging.error(" *** fail ", url, "brow", browser, "headless", headless, "stealth", stealth, "danger", danger, "dedicated", dedicated_selector, "popup", popup_xpath)
        logging.error(f"Failed to capture or download content from {url}")

    return False


def check_if_modified(url, headers) -> bool:
    """
    Determines if a URL has changed since the last request by checking Last-Modified and ETag headers.

    Args:
        url (str): The URL being checked.
        headers (dict): The response headers from the latest request.

    Returns:
        bool: True if the content is new or changed, False if unchanged.
    """
    last_modified = headers.get("Last-Modified")
    etag = headers.get("ETag")

    if last_modified and last_modified == last_modified_cache.get(url):
        logging.debug("No Last-Modified change: %s", last_modified)
        return False  # No changes detected
    if etag and etag == etag_cache.get(url):
        logging.debug("No ETag change: %s", etag_cache)
        return False  # No changes detected

    # Update cache with new values
    if last_modified:
        last_modified_cache[url] = last_modified
    if etag:
        etag_cache[url] = etag

    return True  # Content has changed or was never checked before


def get_content_type(
    url, danger, stealth=False, username=None, password=None
) -> (str, bool):
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
    # Check cache first
    if (
        last_camera_header.get(url)
        and last_camera_header_time.get(url, 0) > time.time() - 60 * 60
    ):
        return last_camera_header.get(url), True

    if "http" not in url or danger:
        return "", True

    content_type = ""
    methods = [requests.head, requests.get]

    lua = UA
    if stealth:
        lua = random_user_agent()

    sess = http_session()
    modified = True
    content_type = ""

    for verb in ("HEAD", "GET"):  # fallback to GET if HEAD blocked
        try:
            # extra header only for the GET probe
            hdrs = {"Range": "bytes=0-1024"} if verb == "GET" else {}
            auth = get_auth(url, username, password)
            resp = sess.request(
                verb,
                url,
                headers=hdrs,
                auth=auth,
                allow_redirects=True,
                timeout=5,
                stream=(verb == "GET"),
            )

            if resp.status_code == 401 and auth:  # retry w/ Digest
                auth = get_digest_auth(url)
                resp = sess.request(
                    verb,
                    url,
                    headers=hdrs,
                    auth=auth,
                    allow_redirects=True,
                    timeout=5,
                    stream=(verb == "GET"),
                )

            if resp.status_code >= 400:
                logging.info(f"HTTP error {resp.status_code} for {url}")
                set_cached_status_code(url, resp.status_code)
                return "", False

            modified = check_if_modified(url, resp.headers)
            content_type = resp.headers.get("Content-Type", "").lower()
            break  # success → stop loop
        except Exception as e:
            logging.info(f"{verb} {url} failed: {e}")

    """
    modified = True
    for method in methods:
        try:
            headers = {"user-agent": lua}
            if method == requests.get:
                headers["Range"] = "bytes=0-1024"

            auth = get_auth(url, username, password)
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

            if response.status_code >= 400:
                logging.info(f"HTTP error {response.status_code} for {url}")
                set_cached_status_code(url, response.status_code)
                return "", False

            modified = check_if_modified(url, response.headers)

            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            break  # Exit the loop if successful
        except Exception as e:
            logging.info(f"Error {method.__name__.upper()} {url}: {e}")
    """

    # Cache the result
    if content_type:
        last_camera_header[url] = content_type
        last_camera_header_time[url] = time.time()

    return content_type, modified


def get_auth(url, username=None, password=None):
    """Return :class:`HTTPBasicAuth` if credentials are available."""
    auth_match = re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url)
    if auth_match:
        return requests.auth.HTTPBasicAuth(*auth_match[0])
    if username and password:
        return requests.auth.HTTPBasicAuth(username, password)
    return None


def get_digest_auth(url, username=None, password=None):
    """Return :class:`HTTPDigestAuth` if credentials are available."""
    auth_match = re.findall(r"\/\/([^\:]+?)\:([^\@]+?)\@", url)
    if auth_match:
        return requests.auth.HTTPDigestAuth(*auth_match[0])
    if username and password:
        return requests.auth.HTTPDigestAuth(username, password)
    return None


def is_image_url(url, content_type):
    """Check if the URL is likely to be an image."""
    image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".gif", "/picture"]
    return (
        any(ext in url.lower() for ext in image_extensions) or "image/" in content_type
    )


def is_pdf_url(url, content_type):
    """Check if the URL is likely to be a PDF."""
    return ".pdf" in url.lower() or "/pdf" in content_type


def is_video_stream_url(url, content_type):
    """Check if the URL is likely to be a video stream."""
    video_indicators = [".mjpg", ".mp4", ".gif", ".webp", "rtsp://", ".m3u8", ":5004/"]
    return (
        any(ind in url.lower() for ind in video_indicators) or "video/" in content_type
    )


def should_use_lightweight_browser(
    url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
):
    """Determine if a lightweight browser should be used for capture."""

    # print("   <<<<", dedicated_selector, "pop", popup_xpath, "stealth", stealth, browser, is_enhanced(url), danger)
    return (
        re.findall(r"^https?://", url, flags=re.I)
        and dedicated_selector in [None, ""]
        and popup_xpath in [None, ""]
        and not stealth
        and not browser
        and not headless
        and not is_enhanced(url)
        and not danger
    )


def should_use_phantom_browser(
    url, dedicated_selector, popup_xpath, headless, stealth, browser, danger
):
    """Determine if a lightweight browser should be used for capture."""
    return (
        re.findall(r"^https?://", url, flags=re.I)
        and
        # dedicated_selector in [None, ""] and
        # popup_xpath in [None, ""] and
        not stealth
        and not browser
        and not is_enhanced(url)
        and not danger
    )


# The rest of the functions (download_image, download_pdf, capture_frame_from_stream,
# capture_frame_with_ytdlp, capture_screenshot_and_har_light, capture_screenshot_and_har)
# should be implemented as before, with appropriate error handling and logging.


def capture_frame_with_ytdlp(url, output_path, name="unknown", invert=False):
    """
    Use yt-dlp to get the video URL, then ffmpeg to capture a single frame from that video.
    """
    # Quick check for yt-dlp
    if shutil.which("yt-dlp") is None:
        logging.error("yt-dlp is not installed or not in the system path.")
        return False

    if (
        lurl_cache.get(url, "none") != "good"
        and time.time() - lurl_cache_time.get(url, 0) < 3600
    ):  # try every 1 hour no matter what??
        # don't keep retrying on known bad
        logging.debug("skipping %s %s", lurl_cache[url], url)
        return False

    lsuccess = False
    try:
        lurl_cache_time[url] = time.time()
        # 1) Use yt-dlp to retrieve the direct video URL
        ytdlp_command = [
            "yt-dlp",
            "--get-url",
            # "--format",
            # "bestvideo",  # note, don't specify this or it will screw up on streams without audio (common)
            url,
        ]
        result = subprocess.run(
            ytdlp_command,
            # check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CAPTURE_TIMEOUT,
        )

        # Note! check the result. If the return code isnt 0, then we should fail out.  Why though? Check on that too.

        if result.returncode != 0:
            lurl_cache[url] = "bad"
            if re.findall(
                r"(?:vailable|found|404)", result.stderr.decode("utf-8").lower()
            ):
                lurl_cache[url] = "offline"
                # print("offline", url)
            return False

        lurl_cache[url] = "good"
        video_url = result.stdout.decode().strip()

        # Validate the video_url to ensure it is a legitimate URL
        parsed_url = urlparse(video_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logging.error(f"Invalid video URL: {video_url}")
            return False

        # 2) Use ffmpeg to capture a single frame
        ffmpeg_command = [FFMPEG_PATH]
        if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
            ffmpeg_command += ["-hwaccel", FFMPEG_HWACCEL]
        ffmpeg_command += [
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
            stderr=subprocess.PIPE,
            timeout=CAPTURE_TIMEOUT,
        )

        # 3) Check output; add timestamp
        if os.path.exists(output_path) and _is_valid_png(output_path):
            add_timestamp(output_path, name=name, invert=invert)
            logging.debug(f"Successfully captured frame with ytdlp+ffmpeg: {url}")
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
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    stealth=False,
):
    """Use ffmpeg to capture multiple frames from a video stream and save the last one."""

    if timeout < 5:
        timeout = 5

    tmpdirname = f"/tmp/glimpser_{name}"
    os.makedirs(tmpdirname, exist_ok=True)
    if os.path.exists(tmpdirname):
        # Capture multiple frames into the temporary directory
        temp_output_pattern = os.path.join(tmpdirname, "frame_%03d.png")
        command = [
            FFMPEG_PATH,  # Use the configurable FFMPEG_PATH
            "-hide_banner",
        ]
        if FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false":
            command.extend(["-hwaccel", FFMPEG_HWACCEL])

        lua = UA
        if stealth:
            chrome_path = get_chrome_path()
            cv = get_chrome_version(chrome_path)
            lua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36"
                % cv
            )

        probe_size = PROBE_SIZE_DEFAULT
        analyze_duration = ANALYZE_DURATION_DEFAULT
        if "http:" in url or "https:" in url:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            command.extend(["-headers", "User-Agent: %s\r\n" % lua])
            command.extend(["-headers", f"referer: {base_url}\r\n"])
            command.extend(["-headers", f"origin: {base_url}\r\n"])
            command.extend(["-seekable", "0"])
            # command.extend(['-timeout', str(CAPTURE_TIMEOUT-1)])  # not sure why, but this causes us a lot of issues, dont set a timetout
            probe_size = PROBE_SIZE_DEFAULT
            analyze_duration = ANALYZE_DURATION_DEFAULT
        elif "rtsp:" in url:
            command.extend(["-rtsp_transport", "tcp"])
            probe_size = PROBE_SIZE_RTSP
            analyze_duration = ANALYZE_DURATION_RTSP
            if "/streaming/" in url.lower():  # alittle bit of a hack
                command.extend(["-c:v", "h264"])
                command.extend(["-r", "1"])
                probe_size = PROBE_SIZE_OTHER
                analyze_duration = ANALYZE_DURATION_OTHER
        else:
            probe_size = PROBE_SIZE_OTHER
            analyze_duration = ANALYZE_DURATION_OTHER

        # Use configured analyze duration and probe size values
        command.extend(["-analyzeduration", analyze_duration])
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
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logging.error("ffmpeg timed out for %s after %ss", url, timeout)
            return False
        except subprocess.CalledProcessError as e:
            logging.error(
                "ffmpeg failed for %s: %s",
                url,
                e.stderr.decode("utf-8", "ignore")[:200],
            )
            return False
        except Exception as e:
            logging.error("Error running ffmpeg for %s: %s", url, e)
            return False

        try:
            # Sort the captured frames by size and take the last one
            frames = sorted(
                os.listdir(tmpdirname),
                key=lambda x: os.path.getsize(os.path.join(tmpdirname, x)),
            )
            if frames:
                last_frame_path = os.path.join(tmpdirname, frames[-1])
                # Move the last frame to the output path
                shutil.move(last_frame_path, output_path)
                if os.path.exists(output_path) and _is_valid_png(output_path):
                    add_timestamp(output_path, name=name, invert=invert)
                    logging.debug(f"Successfully captured frame from stream {url}")
                    return True
            else:
                logging.error(f"No frames captured from stream {url}")
        except Exception as e:
            logging.error(f"Error capturing frames from stream: {e}")

    logging.error(f"Error capturing frame with {FFMPEG_PATH}: {url}")
    return False


def apply_dark_mode(img, rng=30, txt_rng=120):
    arr = np.asarray(
        img.convert("RGB")
    ).copy()  # copy to avoid "assignment destination is read-only" errors
    dark = arr <= rng
    light = arr >= 255 - txt_rng
    mask = dark.any(axis=-1) | light.any(axis=-1)
    arr[mask] = 255 - arr[mask]
    return Image.fromarray(arr)


def capture_screenshot_and_har_light(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    proxy=None,
    dark=True,
    stealth=False,
):
    """
    Capture a screenshot of a URL using wkhtmltoimage (WebKit).
    """
    proxy = validate_proxy(proxy)
    url = validate_url(url)
    if url is None:
        logging.warning("Invalid URL provided for screenshot capture")
        return False
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

    lua = UA
    if stealth:
        chrome_path = get_chrome_path()
        cv = get_chrome_version(chrome_path)
        lua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36"
            % cv
        )

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
        lua,
        "--custom-header-propagation",
        url,
        tmp_path,
    ]

    try:
        # Run wkhtmltoimage
        result = subprocess.run(
            command,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

        if result.returncode != 0:
            # logging.warning(f"wkhtmltoimage failed (returncode {result.returncode}): {result.stderr.decode('utf-8','ignore')}")
            logging.warning(f"wkhtmltoimage failed (returncode {result.returncode}): ")
            return False

        # Process the output file
        if not os.path.exists(tmp_path):
            return False

        # Open and convert the image
        with Image.open(tmp_path) as image:
            image = image.convert("RGB")  # ensure RGB
            if is_mostly_blank(image):
                logging.warning(
                    f"Captured image is mostly blank—skipping. {url} {name}"
                )
                os.unlink(tmp_path)
                return False

            image = remove_background(image)
            if dark:
                image = apply_dark_mode(image)
            image.save(tmp_path, "PNG")

        # Rename from .tmp.png to final .png
        # Validate the temporary file before renaming so we don't
        # replace the output with an incomplete image.
        if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
            add_timestamp(tmp_path, name, invert=invert)
            os.rename(tmp_path, output_path)
            lsuccess = True

        # If you capture HAR data, do that here as well...
        logging.debug(
            f"Successfully captured light screenshot for {url} at {output_path} "
            f"({round(time.time() - start_time, 3)}s)"
        )
        return lsuccess

    except subprocess.TimeoutExpired:
        logging.warning("wkhtmltoimage timed out for %s after %ss", url, timeout)
        return False
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


def get_chrome_path():
    """
    paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    """
    return (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )


def get_chrome_version(chrome_path):
    # Command to get the installed version of Chrome
    if (
        chrome_version.get(chrome_path) is not None
        and chrome_version[chrome_path][1] > time.time() - 60 * 60
    ):
        return int(chrome_version[chrome_path][0])

    try:
        result = subprocess.run(
            [chrome_path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        version = result.stdout.strip().split()[-1]
        version = int(version.split(".")[0])  # Return the major version
        chrome_version[chrome_path] = (version, time.time())
    except Exception as e:
        logging.error(f"Chrome version exception error: {e}")
        return chrome_version.get(chrome_path, extract_version())

    return int(version)


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
        logging.error(
            "Error extracting version from path: %s, error: %s", driver_path, e
        )
        # Default to a known working version if extraction fails
        return 135


def is_port_open(host, port, timeout=5):
    """Check if a network port is open on the specified host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((host, port))
        except OSError:
            return False
        if result == 0:
            return True
        if host in ("google.com", "www.google.com") and port == 80:
            return True
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


def kill_driver_process(driver):
    """Kills the Chrome process associated with the given driver."""
    try:
        time.sleep(5)
        if driver.service.process and driver.service.process.pid:
            pid = driver.service.process.pid
            chrome_process = psutil.Process(pid)
            for child in chrome_process.children(recursive=True):
                if psutil.pid_exists(child.pid):
                    child.terminate()
                    child.wait(timeout=5)
            if psutil.pid_exists(pid):
                chrome_process.terminate()
                logging.debug("TERMINATE %s", driver)
                chrome_process.wait(timeout=5)
    except psutil.NoSuchProcess:
        logging.debug(f"Process {pid} already exited before termination attempt.")
    except Exception as e:
        logging.error(f"Error killing Chrome process: {e}")
    finally:
        # Ensure future calls create a new driver
        global _DRIVER
        _DRIVER = None


def launch_headless_chrome(driver_options, version=None):

    driver = None
    try:
        # note - version not working
        # service = Service(ChromeDriverManager(version=str(version)).install())
        # service = Service(ChromeDriverManager().install())
        # driver = webdriver.Chrome(service=service, options=driver_options)
        driver = get_driver(driver_options)
        # driver = webdriver.Chrome(service=service, options=driver_options, version_main=version)
        # driver = uc.Chrome(options=driver_options, version_main=version)
    except Exception as e:
        logging.error("BAD DRIVER ERROR %s", e)
        # _purge_driver_cache() # maybe?
    return driver


def apply_stealth_options(driver_options):
    """Randomize options to better mimic a human browser."""
    width = random.randint(1200, 1920)
    height = random.randint(800, 1080)
    driver_options.add_argument(f"--window-size={width},{height}")
    driver_options.add_argument(f"--user-agent={random_user_agent()}")
    driver_options.add_argument("--disable-blink-features=AutomationControlled")
    driver_options.add_argument("--disable-infobars")
    driver_options.add_argument("--disable-extensions")


def _purge_driver_cache():
    """
    Remove the undetected_chromedriver or webdriver_manager cache so that
    on next run it will download a fresh driver matching the current Chrome version.
    """
    # undetected_chromedriver stores its driver at ~/.local/share/undetected_chromedriver
    # webdriver_manager in ~/.wdm etc. Adjust as needed:

    uc_cache_dir = os.path.expanduser("~/.local/share/undetected_chromedriver")
    if os.path.isdir(uc_cache_dir):
        logging.info(f"Removing undetected_chromedriver cache: {uc_cache_dir}")
        time.sleep(1)
        shutil.rmtree(uc_cache_dir, ignore_errors=True)

    # If you're using webdriver_manager:
    wdm_cache_dir = os.path.expanduser("~/.wdm")
    if os.path.isdir(wdm_cache_dir):
        logging.info(f"Removing webdriver_manager cache: {wdm_cache_dir}")
        shutil.rmtree(wdm_cache_dir, ignore_errors=True)


def capture_screenshot_phantom(
    url,
    output_path,
    timeout=10,
    name="unknown",
    invert=False,
    dark=False,
    above_fold_only=True,
    popup_xpath=None,
    dedicated_selector=None,
    viewport_width=1920,
    viewport_height=1080,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36"
    ),
):
    import os
    import logging
    import shutil
    import subprocess
    from PIL import Image

    if shutil.which("phantomjs") is None:
        logging.warning("PhantomJS not found; cannot capture screenshot.")
        return False

    if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        url = "https://" + url

    if timeout < 15:
        timeout = 15
    timeout = int(timeout)

    # Safely escape backslashes and quotes in XPaths
    safe_popup_xpath = ""
    safe_dedicated_selector = ""
    if popup_xpath:
        safe_popup_xpath = popup_xpath.replace("\\", "\\\\").replace('"', '\\"')
    if dedicated_selector:
        safe_dedicated_selector = dedicated_selector.replace("\\", "\\\\").replace(
            '"', '\\"'
        )

    remove_popup_script = ""
    if popup_xpath:
        remove_popup_script = f"""
            page.evaluate(function() {{
                var snapshot = document.evaluate("{safe_popup_xpath}", document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                for (var i = 0; i < snapshot.snapshotLength; i++) {{
                    var node = snapshot.snapshotItem(i);
                    if (node && node.parentNode) {{
                        node.parentNode.removeChild(node);
                    }}
                }}
            }});
        """

    dedicated_selector_script = ""
    if dedicated_selector:
        dedicated_selector_script = f"""
            var rect = page.evaluate(function() {{
                var el = document.evaluate("{safe_dedicated_selector}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!el) return null;
                var b = el.getBoundingClientRect();
                return {{
                    top: b.top,
                    left: b.left,
                    width: b.width,
                    height: b.height
                }};
            }});
            if (rect) {{
                page.clipRect = rect;
            }}
        """

    tmpdir = f"/tmp/glimpser_{name}"
    os.makedirs(tmpdir, exist_ok=True)
    if os.path.exists(tmpdir):  # check if writeable too...
        script_path = os.path.join(tmpdir, "capture.js")
        screenshot_tmp = os.path.join(tmpdir, "phantom_out.png")

        phantom_script = f"""
            var page = require('webpage').create();
            page.settings.ignoreSslErrors = true;
            page.settings.sslProtocol = 'any';
            page.settings.userAgent = "{user_agent}";
            page.settings.loadImages = true;
            page.settings.resourceTimeout = 55000;
            page.viewportSize = {{
                width: {viewport_width},
                height: {viewport_height}
            }};
            if ({str(above_fold_only).lower()}) {{
                page.clipRect = {{
                    top: 0,
                    left: 0,
                    width: {viewport_width},
                    height: {viewport_height}
                }};
            }}

            function waitForImages(callback) {{
                var startTime = Date.now();
                var maxWaitTime = 20000;
                function checkImages() {{
                    var ready = page.evaluate(function() {{
                        var imgs = document.images;
                        for (var i=0; i<imgs.length;i++) {{
                            if(!imgs[i].complete) return false;
                        }}
                        return true;
                    }});
                    if(ready || (Date.now() - startTime) >= maxWaitTime) {{
                        callback();
                    }} else {{
                        setTimeout(checkImages, 500);
                    }}
                }}
                checkImages();
            }}

            page.open("{url}", function(status) {{
                if (status !== 'success') {{
                    page.render("{screenshot_tmp}");
                    phantom.exit(0);
                }} else {{
                    {remove_popup_script}
                    waitForImages(function() {{
                        setTimeout(function() {{
                            {dedicated_selector_script}
                            page.render("{screenshot_tmp}");
                            phantom.exit(0);
                        }}, 2000);
                    }});
                }}
            }});
        """

        with open(script_path, "w") as f:
            f.write(phantom_script)

        try:
            subprocess.run(
                [
                    "phantomjs",
                    "--ignore-ssl-errors=true",
                    "--ssl-protocol=any",
                    "--web-security=false",
                    script_path,
                ],
                timeout=timeout + 10,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            logging.warning(f"PhantomJS timed out for {url}.")
            return False
        except Exception as e:
            logging.warning(f"PhantomJS error for {url}: {e}")
            return False

        if not os.path.exists(screenshot_tmp):
            logging.warning(
                f"PhantomJS script completed but no screenshot found for {url}"
            )
            return False

        try:
            return _finalize_screenshot(
                screenshot_tmp,
                output_path,
                name=name,
                invert=invert,
                dark=dark,
            )
        except Exception as e:
            logging.error(f"Error post-processing Phantom screenshot for {url}: {e}")
            return False


def cleanup_old_tempdirs(prefix="glimpser_", max_age_hours=12):
    """
    Best-effort removal of leftover ephemeral directories older than `max_age_hours`.
    This helps if your program crashed and left behind /tmp/glimpser_XYZ directories.
    """
    now = time.time()
    tmp_root = "/tmp"
    for entry in os.scandir(tmp_root):
        if entry.is_dir() and entry.name.startswith(prefix):
            dir_path = os.path.join(tmp_root, entry.name)
            try:
                st = os.stat(dir_path)
                # If older than max_age_hours, remove it
                if (now - st.st_mtime) > (max_age_hours * 3600):
                    logging.info(f"Removing stale temp directory: {dir_path}")
                    shutil.rmtree(dir_path, ignore_errors=True)
            except Exception as e:
                logging.debug(f"Could not remove {dir_path}: {e}")


def capture_screenshot_and_har_nodriver(
    url: str,
    output_path: str,
    har_output_path: str = None,
    headless: bool = True,
    width: int = 1920,
    height: int = 1080,
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/109.0.5414.120 Safari/537.36"
    ),
    timeout: int = 30,
    enable_dark_mode: bool = False,
) -> bool:
    """
    Capture a screenshot of the given URL and (optionally) store DevTools 'network' events
    to an HAR-like JSON file, all using nodriver (no Selenium/undetected_chromedriver).
    """

    # nodriver can both 'launch()' a new Chrome, or 'connect()' to an already-running instance.
    # Below we launch a fresh headless session for each capture.
    # For efficiency, consider reusing one launch() if you do multiple captures.

    try:
        with nodriver.launch(
            headless=headless,
            extra_args=[
                "--no-sandbox",
                "--disable-gpu",
                f"--window-size={width},{height}",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-translate",
                "--disable-extensions",
                "--disable-sync",
            ],
        ) as browser:
            cdp = browser.connect()

            # Apply user agent override if desired
            if user_agent:
                cdp.send("Network.setUserAgentOverride", userAgent=user_agent)

            # Enable basic events (Page, Network)
            cdp.send("Page.enable")
            cdp.send("Network.enable")

            # Optionally turn on "dark mode"
            if enable_dark_mode:
                try:
                    cdp.send("Emulation.setAutoDarkModeOverride", enabled=True)
                except Exception as dark_ex:
                    logging.warning(f"Dark mode override failed: {dark_ex}")

            # Collect network requests if you want to store a HAR-like log
            network_events = []

            def on_event(msg):
                # Only store Network.* events
                if msg.get("method", "").startswith("Network."):
                    network_events.append(msg)

            cdp.add_listener("*", on_event)

            # Set viewport size
            browser.set_viewport_size(width, height)

            # Navigate to the URL
            cdp.send("Page.navigate", url=url)

            # Wait until 'Page.loadEventFired' (i.e., DOM load)
            finished = cdp.wait("Page.loadEventFired", timeout=timeout)
            if not finished:
                logging.warning(f"Timeout waiting for {url} to load.")
                return False

            # A short additional sleep can help ensure images, JS, etc. are fully settled
            time.sleep(2)

            # Capture a screenshot (returns base64)
            resp = cdp.send("Page.captureScreenshot", format="png")
            data_b64 = resp.get("data")
            if not data_b64:
                logging.error("No screenshot data returned.")
                return False

            # Decode and write the PNG
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(data_b64))

            logging.debug(f"Screenshot saved to {output_path}")

            # Optionally save a JSON log of the network events
            if har_output_path:
                with open(har_output_path, "w", encoding="utf-8") as harf:
                    json.dump(network_events, harf, indent=2)
                logging.debug(f"Network events saved to {har_output_path}")

            return True

    except Exception as e:
        logging.error(f"Error using nodriver for {url}: {e}")
        return False


########################################
# The "Tough" capture_screenshot_and_har
########################################


def capture_screenshot_and_har(
    url: str,
    output_path: str,
    timeout: int = 30,
    name: str = "unknown",
    popup_xpath: str = None,
    dedicated_selector: str = None,
    invert: bool = False,
    proxy: str = None,
    headless: bool = True,
    stealth: bool = True,
    dark: bool = False,
    danger: bool = False,
    # If you want to store the captured HAR logs:
    har_output_path: str = None,
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

    proxy = validate_proxy(proxy)

    # Quick sanity check
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        logging.error(f"[capture_screenshot_and_har] Not a valid http/https URL: {url}")
        return False

    if timeout < 30:
        timeout = 30

    cleanup_old_tempdirs(prefix="glimpser_", max_age_hours=12)

    chrome_path = get_chrome_path()
    if chrome_path is None:
        return False

    # We'll do a partial screenshot path first
    partial_screenshot = output_path + ".tmp.png"
    success = False

    ############
    # Danger Mode
    ############
    if danger and config.get_setting("DANGER_MODE", "True") == "True":
        # If we rely on the user's local Chrome with remote-debugging-port=9222,
        # let's confirm it's actually open.
        if not is_chrome_debug_port_open("127.0.0.1", 9222):
            logging.warning(
                f"[capture_screenshot_and_har] Danger mode requested, but no Chrome on port 9222."
            )
            return False

        # Optionally, skip if we detect user activity (like your `check_user_activity`).
        # from app.utils.screenshots import check_user_activity
        if check_user_activity(timeout=10):
            # print("skipping danger mode", name)
            logging.warning(
                "User is active; skipping Danger screenshot to avoid messing with user’s browser."
            )
            return False

        # print("not skipping danger mode", name)
        return _capture_danger_mode(
            url,
            partial_screenshot,
            popup_xpath,
            dedicated_selector,
            timeout,
            name,
            invert,
            dark,
        ) and _finalize_screenshot(partial_screenshot, output_path, name, invert, dark)

    ##################
    # Non-Danger Mode
    ##################
    user_data_dir = None
    driver = None
    try:
        # Create ephemeral profile dir in /tmp
        tmp_profile = f"/tmp/glimpser_{name}"
        os.makedirs(tmp_profile, exist_ok=True)
        user_data_dir = tmp_profile  # just to keep track

        # Using undetected_chromedriver for stealth:
        # driver_options = uc.ChromeOptions()
        driver_options = Options()
        if headless:
            # For Chrome 109+, "headless=new" is recommended; fallback if it fails
            driver_options.add_argument("--headless=new")

        # Key ephemeral & performance log settings
        driver_options.add_argument(f"--user-data-dir={tmp_profile}")
        driver_options.add_argument("--no-sandbox")
        driver_options.add_argument("--disable-dev-shm-usage")
        driver_options.add_argument("--disable-gpu")
        if stealth:
            apply_stealth_options(driver_options)
        else:
            driver_options.add_argument("--window-size=1920,1080")
            driver_options.add_argument("--disable-blink-features=AutomationControlled")
            driver_options.add_argument("--enable-automation")
        driver_options.add_argument("--disable-infobars")
        driver_options.add_argument("--disable-background-networking")
        driver_options.add_argument("--disable-features=TranslateUI")
        driver_options.add_argument("--disable-background-timer-throttling")
        driver_options.add_argument("--disable-backgrounding-occluded-windows")
        driver_options.add_argument("--disable-breakpad")
        driver_options.add_argument(
            "--disable-component-extensions-with-background-pages"
        )  # Disables unnecessary extensions
        driver_options.add_argument(
            "--disable-client-side-phishing-detection"
        )  # Speeds up execution
        driver_options.add_argument(
            "--disable-default-apps"
        )  # Prevents default apps from loading
        driver_options.add_argument(
            "--disable-hang-monitor"
        )  # Prevents Chrome from freezing when unresponsive
        driver_options.add_argument(
            "--disable-ipc-flooding-protection"
        )  # Prevents IPC issues
        driver_options.add_argument(
            "--disable-renderer-backgrounding"
        )  # Ensures no CPU throttling
        if not stealth:
            driver_options.add_argument(
                "--enable-automation"
            )  # Explicitly marks as automation-friendly
        driver_options.add_argument(
            "--force-device-scale-factor=1"
        )  # Prevents UI scaling issues
        driver_options.add_argument(
            "--force-color-profile=srgb"
        )  # Prevents color space issues
        driver_options.add_argument(
            "--metrics-recording-only"
        )  # Reduces telemetry load
        driver_options.add_argument(
            "--safebrowsing-disable-auto-update"
        )  # Reduces network requests
        driver_options.add_argument("--disable-translate")  # Prevents translation UI
        driver_options.add_argument("--no-first-run")  # Skips first-time setup
        driver_options.add_argument(
            "--disable-notifications"
        )  # Disables notification popups
        driver_options.add_argument("--disable-extensions")  # Reduces memory footprint
        driver_options.add_argument("--disable-site-isolation-trials")

        # Performance logs → HAR-like data
        # driver_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        if proxy:
            driver_options.add_argument(f"--proxy-server={proxy}")

        version = get_chrome_version(chrome_path)

        driver = launch_headless_chrome(driver_options, version=version)
        if driver is None:
            _purge_driver_cache()
            driver = launch_headless_chrome(driver_options, version)
            if driver is None:
                logging.error("missing driver!")
                raise ValueError("missing driver!")

        driver.set_page_load_timeout(timeout)
        # Attempt dark mode for the loaded page, if desired
        if dark and not invert:
            try:
                driver.execute_cdp_cmd(
                    "Emulation.setAutoDarkModeOverride", {"enabled": True}
                )
            except Exception as e:
                logging.debug(f"Failed to setAutoDarkModeOverride: {e}")

        # Navigate
        driver.get(url)
        time.sleep(
            5
        )  # Basic wait for DOM. Tweak as needed or switch to explicit waits.

        # Remove popups
        if popup_xpath:
            try:
                _remove_popup(driver, popup_xpath)
            except Exception as e:
                # logging.info(f"Could not remove popup={popup_xpath}:")
                pass

        # If dedicated_selector is set, capture that region instead of full page
        if dedicated_selector:
            try:
                element = driver.find_element(By.XPATH, dedicated_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)
                element.screenshot(partial_screenshot)
            except Exception as e:
                pass

        # Fallback to entire page if partial didn't get created
        if not os.path.exists(partial_screenshot):
            driver.save_screenshot(partial_screenshot)

        # Attempt to gather performance logs → HAR
        # if har_output_path:
        #    _save_har_logs(driver, har_output_path)

        # Post-process final
        success = _finalize_screenshot(
            partial_screenshot, output_path, name, invert, dark
        )

    except TimeoutException as e:
        logging.warning(f"[capture_screenshot_and_har] Timeout error for {url}")
    except WebDriverException as e:
        logging.warning(f"[capture_screenshot_and_har] WebDriver error for {url}")
    except Exception as e:
        logging.error(f"[capture_screenshot_and_har] Unexpected error: {url} {e}")
    finally:
        # Gracefully close the driver
        if driver:
            try:
                driver.quit()
                time.sleep(1)
            except Exception as ex:
                logging.warning("driver.quit() failed: %s", ex)
            # Force-kill child processes if needed
            kill_driver_process(driver)

        # Remove ephemeral user-data-dir
        if user_data_dir and os.path.exists(user_data_dir):
            try:
                shutil.rmtree(user_data_dir, ignore_errors=True)
            except Exception as e:
                logging.debug(f"Could not remove ephemeral dir {user_data_dir}: {e}")

        if user_data_dir and os.path.exists(user_data_dir):
            logging.warning("data dir did not clean, %s", user_data_dir)

    return success


######################
# Helper subroutines #
######################


def _finalize_screenshot(tmp_path, final_path, name, invert, dark):
    """
    Checks if tmp_path exists, does some post-processing, and renames to final_path.
    Returns True on success, False otherwise.
    """
    if not os.path.exists(tmp_path):
        return False

    try:
        with Image.open(tmp_path) as img:
            img = img.convert("RGB")

            if is_mostly_blank(img):
                logging.warning(f"[{name}] The captured screenshot looks mostly blank.")
                os.remove(tmp_path)
                return False

            # Optional background removal
            img = remove_background(img)

            # If you want to do naive “darkening” or inverting more thoroughly,
            # you can do that here. For example:
            # if dark:
            #    img = apply_dark_mode(img)

            # Save back
            img.save(tmp_path, "PNG")

        # Now add a timestamp overlay
        add_timestamp(tmp_path, name=name, invert=invert)

        # Finally rename
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        os.rename(tmp_path, final_path)

        logging.debug(f"SAVED screenshot -> {final_path}")
        return True

    except Exception as e:
        logging.error(f"Screenshot finalization error: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _capture_danger_mode(
    url,
    partial_screenshot,
    popup_xpath,
    dedicated_selector,
    timeout,
    name,
    invert,
    dark,
) -> bool:
    """
    Attach to an existing local Chrome with remote-debugging-port=9222,
    open a new tab, capture a screenshot, close the tab, and yield the result.

    Because we are hooking into a real user’s Chrome, you must be aware that
    you can break them if you do something invasive. Also, Chrome or the user
    might close the new tab any time.

    Return True if partial_screenshot was created, else False.
    """
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import TimeoutException

    # This part uses normal Selenium for the attach:
    danger_options = webdriver.ChromeOptions()
    danger_options.debugger_address = "127.0.0.1:9222"

    driver = None
    original_window = None
    new_tab_handle = None

    try:
        driver = webdriver.Chrome(options=danger_options)
        driver.set_page_load_timeout(timeout)

        # Record the existing window we were in
        original_window = driver.current_window_handle

        # Open a new blank tab, then navigate
        driver.execute_script("window.open('about:blank','_blank');")
        time.sleep(0.5)
        all_tabs = driver.window_handles
        new_tab_handle = all_tabs[-1]  # the newly opened blank
        driver.switch_to.window(new_tab_handle)
        logging.debug("trying %s", url)
        driver.get(url)
        logging.debug("success, screenshotting %s", url)
        _send_input_event()
        time.sleep(3)

        # Attempt dark mode if desired
        if dark and not invert:
            try:
                driver.execute_cdp_cmd(
                    "Emulation.setAutoDarkModeOverride", {"enabled": True}
                )
            except Exception as e:
                logging.debug(f"[danger_mode] setAutoDarkModeOverride failed: {e}")
        time.sleep(5)

        # Remove popups
        if popup_xpath:
            _remove_popup(driver, popup_xpath)

        # Dedicated selector
        if dedicated_selector:
            try:
                el = driver.find_element(By.XPATH, dedicated_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", el)
                time.sleep(5)
                el.screenshot(partial_screenshot)
            except Exception as e:
                logging.warning(f"[danger_mode] dedicated_selector error: {e}")

        # Fallback entire page
        if not os.path.exists(partial_screenshot):
            driver.save_screenshot(partial_screenshot)

        return os.path.exists(partial_screenshot)

    except TimeoutException:
        # print("timeout1")
        logging.warning(f"[danger_mode] Timeout while loading page: {url}")
        return False
    except Exception as e:
        logging.error("[danger_mode] Unexpected error: %s", e)
        return False
    finally:
        # Close just our new tab
        try:
            if new_tab_handle:
                driver.switch_to.window(new_tab_handle)
                driver.close()
        except Exception as ex:
            logging.debug(f"Could not close new tab in danger mode: {ex}")

        # Switch back to the original window
        if original_window:
            try:
                driver.switch_to.window(original_window)
            except Exception as ex:
                logging.debug(
                    f"Could not switch to original window in danger mode: {ex}"
                )

        # DO NOT do driver.quit() in Danger mode: that kills the user's entire Chrome
        driver = None


def _remove_popup(driver, popup_xpath):
    """
    If there's an annoying overlay or popup, remove it from the DOM by XPATH.
    """
    try:
        elements = driver.find_elements(By.XPATH, popup_xpath)
        for el in elements:
            driver.execute_script("arguments[0].remove();", el)
    except Exception as e:
        logging.debug(f"_remove_popup error: {e}")


def _save_har_logs(driver, har_output_path):
    """
    Grab performance logs from Chrome and write them to a file (JSON).
    This is not a perfect HAR, but it’s close enough for many cases.
    """
    try:
        logs = driver.get_log("performance")
        # logs is a list of dict with keys: { "level": str, "message": str, "timestamp": int }

        with open(har_output_path, "w", encoding="utf-8") as f:
            for entry in logs:
                f.write(entry["message"] + "\n")
        logging.debug(f"Saved HAR-like logs -> {har_output_path}")

    except Exception as e:
        logging.error(f"Could not fetch performance logs: {e}")


def create_blank_frame(name: str, size=(1280, 720)) -> str:
    """Generate a blank screenshot for ``name``.

    A timestamp and camera name are added so the resulting image can be
    spliced into video sequences when templates change.

    Parameters
    ----------
    name : str
        Template identifier used to determine the storage path.

    size : tuple, optional
        Image width and height. Defaults to ``(1280, 720)``.

    Returns
    -------
    str
        Absolute path to the created image.
    """

    output_dir = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name))
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    image_path = os.path.join(output_dir, f"{name}_{timestamp}_blank.png")

    image = Image.new("RGB", size, (0, 0, 0))
    image.save(image_path, "PNG")
    add_timestamp(image_path, name=name)

    return image_path
