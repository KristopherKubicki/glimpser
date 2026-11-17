"""Interact with Chrome binaries for version and networking checks.

This module locates the Chrome or Chromium executable, extracts the
installed version, tests GPU and debugging capabilities and exposes a
utility for checking if arbitrary TCP ports are open.  The helpers are
used by screenshot capture and to validate runtime environments.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import time

from app import config

# Cache for Chrome versions and GPU capability results
chrome_version: dict[str, tuple[int, float]] = {}
_GL_CACHE_PATH = "data/chrome_gl_probe.sqlite3"
_GL_CACHE_SECONDS = 300


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
        version_output = f"{result.stdout} {result.stderr}".strip()
        match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", version_output)
        if not match:
            raise ValueError("Version number not found in command output.")
        version = int(match.group(1))
        chrome_version[chrome_path] = (version, time.time())
    except Exception as exc:
        logging.error("Chrome version exception error: %s", exc)
        return chrome_version.get(chrome_path, extract_version(chrome_path))

    return int(version)


def _probe_browser_gl(chrome_path: str) -> bool:
    """Run the existing isolated Chrome capability check."""
    try:
        subprocess.check_call(
            [
                chrome_path,
                "--headless=new",
                "--use-gl=egl",
                "--dump-dom",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except Exception:
        return False


def browser_supports_gl(chrome_path: str) -> bool:
    """Share a five-minute capability result across short-lived capture workers.

    SQLite serializes the check itself, so simultaneous cold workers launch only
    one probe. Binary metadata invalidates upgrades; the TTL limits stale results
    following driver or runtime changes. No page or camera data enters this cache.
    """
    connection = None
    result = None
    try:
        stat = os.stat(chrome_path)
        identity = (
            os.path.realpath(chrome_path),
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            os.getuid(),
        )
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        os.makedirs(os.path.dirname(os.path.abspath(_GL_CACHE_PATH)), exist_ok=True)
        connection = sqlite3.connect(_GL_CACHE_PATH, timeout=10)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS probe "
            "(key TEXT PRIMARY KEY, checked REAL NOT NULL, supported INTEGER NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT checked, supported FROM probe WHERE key = ?", (key,)
        ).fetchone()
        now = time.time()
        if row is not None and 0 <= now - row[0] < _GL_CACHE_SECONDS:
            return bool(row[1])
        result = _probe_browser_gl(chrome_path)
        connection.execute(
            "DELETE FROM probe WHERE checked <= ? OR checked > ?",
            (now - _GL_CACHE_SECONDS, now),
        )
        connection.execute(
            "INSERT OR REPLACE INTO probe VALUES (?, ?, ?)",
            (key, time.time(), int(result)),
        )
        connection.commit()
        return result
    except (OSError, sqlite3.Error):
        # Optional caching must not prevent a capture when storage is unavailable.
        return result if result is not None else _probe_browser_gl(chrome_path)
    finally:
        if connection is not None:
            connection.close()


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
