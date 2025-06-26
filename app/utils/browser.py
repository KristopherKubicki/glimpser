"""Utilities for browser-based screenshot capture."""

from __future__ import annotations

import logging
import os
import random
import shutil
import threading
import time
from typing import Optional

import requests
from PIL import ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import app.config as config
from app.config import UA
from .chrome_utils import get_chrome_path, get_chrome_version
from .network import is_system_online

__all__ = [
    "random_user_agent",
    "load_font",
    "get_driver",
    "http_session",
    "apply_stealth_options",
    "purge_driver_cache",
    "reset_cached_driver",
]


FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "LiberationSans-Regular.ttf",
]

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


def random_user_agent() -> str:
    """Return a randomized user agent string."""
    chrome_path = get_chrome_path()
    version = get_chrome_version(chrome_path)
    major_version = random.randint(max(100, version - 1), version + 1)
    template = random.choice(STEALTH_UA_TEMPLATES)
    return template.format(version=major_version)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Return a truetype font for overlays."""
    for font_name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_name, size)
        except IOError:
            continue
    return ImageFont.load_default()


_driver_local = threading.local()
_session: Optional[requests.Session] = None


def get_driver(opts: Options):
    """Return a cached Selenium driver instance."""
    driver = getattr(_driver_local, "driver", None)
    if driver is None:
        if not is_system_online():
            logging.warning("System offline; skipping driver setup")
            return None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            _driver_local.driver = driver
        except Exception as exc:  # pragma: no cover - environment may vary
            logging.error("Failed to launch driver: %s", exc)
            return None
    return driver


def http_session() -> requests.Session:
    """Return a shared requests session."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.verify = False
        _session.headers.update({"user-agent": UA})
        _session.headers.update({"Accept": "*/*"})
        _session.mount("http://", requests.adapters.HTTPAdapter(pool_maxsize=20))
        _session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=20))
    return _session


def apply_stealth_options(driver_options: Options) -> None:
    """Randomize options to better mimic a human browser."""
    width = random.randint(1200, 1920)
    height = random.randint(800, 1080)
    driver_options.add_argument(f"--window-size={width},{height}")
    driver_options.add_argument(f"--user-agent={random_user_agent()}")
    driver_options.add_argument("--disable-blink-features=AutomationControlled")
    driver_options.add_argument("--disable-infobars")
    driver_options.add_argument("--disable-extensions")


def purge_driver_cache() -> None:
    """Remove cached browser drivers."""
    uc_cache_dir = os.path.expanduser("~/.local/share/undetected_chromedriver")
    if os.path.isdir(uc_cache_dir):
        logging.info("Removing undetected_chromedriver cache: %s", uc_cache_dir)
        time.sleep(1)
        shutil.rmtree(uc_cache_dir, ignore_errors=True)

    wdm_cache_dir = os.path.expanduser("~/.wdm")
    if os.path.isdir(wdm_cache_dir):
        logging.info("Removing webdriver_manager cache: %s", wdm_cache_dir)
        shutil.rmtree(wdm_cache_dir, ignore_errors=True)


def reset_cached_driver() -> None:
    """Clear any cached driver from the thread-local store."""
    if hasattr(_driver_local, "driver"):
        _driver_local.driver = None
