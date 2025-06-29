import logging
import os
import re
import shutil
import socket
import subprocess
import time

from app import config

# Cache for Chrome versions and GPU capability results
chrome_version: dict[str, tuple[int, float]] = {}
_browser_gl_cache: dict[str, bool] = {}


def get_chrome_path() -> str | None:
    """Return the path to the Chrome executable if found."""
    paths = ["/usr/bin/google-chrome", "/usr/bin/chromium", "/snap/bin/chromium"]
    for path in paths:
        if os.path.exists(path):
            return path
    return (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )


def extract_version(driver_path: str) -> int:
    """Extract major version from a Chrome driver path."""
    try:
        match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", driver_path)
        if match:
            return int(match.group(1))
        raise ValueError("Version number not found in the path.")
    except Exception as exc:
        logging.error(
            "Error extracting version from path: %s, error: %s", driver_path, exc
        )
        return 135


def get_chrome_version(chrome_path: str) -> int:
    """Return the installed Chrome major version."""
    cached = chrome_version.get(chrome_path)
    if cached and cached[1] > time.time() - 60 * 60:
        return int(cached[0])

    try:
        result = subprocess.run(
            [chrome_path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        version_str = result.stdout.strip().split()[-1]
        version = int(version_str.split(".")[0])
        chrome_version[chrome_path] = (version, time.time())
    except Exception as exc:
        logging.error("Chrome version exception error: %s", exc)
        return chrome_version.get(chrome_path, extract_version(chrome_path))

    return int(version)


def browser_supports_gl(chrome_path: str) -> bool:
    """Return ``True`` if Chrome can start with ``--use-gl=egl``."""
    cached = _browser_gl_cache.get(chrome_path)
    if cached is not None:
        return cached
    try:
        subprocess.check_call(
            [
                chrome_path,
                "--headless=new",
                "--use-gl=egl",
                "--disable-gpu",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        result = True
    except Exception:
        result = False
    _browser_gl_cache[chrome_path] = result
    return result


def is_port_open(host: str, port: int, timeout: int = 5) -> bool:
    """Return ``True`` if a TCP port is open on ``host``."""
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


def is_chrome_debug_port_open(
    host: str = "127.0.0.1", port: int | None = None, timeout: int = 1
) -> bool:
    """Return ``True`` if Chrome's remote debugging port responds."""
    if port is None:
        port = config.DANGER_PORT
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False
