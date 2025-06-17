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


import ctypes
import ctypes.util
import os
import threading
import time

_idle_lock = threading.Lock()
_x11 = None
_xss = None


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
    """Return idle seconds on X11 systems."""

    dpy_name = os.environ.get("DISPLAY")
    if not dpy_name:
        raise RuntimeError("$DISPLAY is not set – not running under X11.")

    global _x11, _xss

    with _idle_lock:
        if _x11 is None or _xss is None:
            libX11_path = ctypes.util.find_library("X11")
            libXss_path = ctypes.util.find_library("Xss")
            if not (libX11_path and libXss_path):
                raise RuntimeError(
                    "libX11 or libXss not found (install libx11-6 libxss1)."
                )

            _x11 = ctypes.cdll.LoadLibrary(libX11_path)
            _xss = ctypes.cdll.LoadLibrary(libXss_path)

            _x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            _x11.XOpenDisplay.restype = ctypes.c_void_p
            _x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            _x11.XDefaultRootWindow.restype = ctypes.c_ulong
            _xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
            _xss.XScreenSaverQueryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(XScreenSaverInfo),
            ]
            _xss.XScreenSaverQueryInfo.restype = ctypes.c_int
            _x11.XFree.argtypes = [ctypes.c_void_p]
            _x11.XFree.restype = None
            _x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            _x11.XCloseDisplay.restype = None

        x11 = _x11
        xss = _xss

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
        return idle_ms // 1000


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
