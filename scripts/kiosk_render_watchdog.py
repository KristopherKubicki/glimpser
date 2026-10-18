"""Recover a kiosk whose rendering heartbeat stopped while Glimpser is reachable."""

import ctypes
import json
import logging
import os
import re
import subprocess
import time
import urllib.request

PROFILE = os.environ.get("GLIMPSER_RENDER_PROFILE", "office")
URL = f"http://glimpser.home.arpa/kiosk_health?profile={PROFILE}"


def should_recover(age, healthy_for, since_restart):
    """Require sustained server connectivity, stale rendering, and a cooldown."""
    if healthy_for < 180 or since_restart < 600:
        return False
    return age > 180 if isinstance(age, (int, float)) else healthy_for >= 300


def kiosk_window_id(tree: str) -> int | None:
    """Identify the fullscreen Glimpser app even when its page title is an error."""
    match = re.search(
        r'^\s*(0x[0-9a-f]+) "[^"\n]*": '
        r'\("glimpser\.home\.arpa" "Google-chrome"\)\s+1920x1080[+-]\d+[+-]\d+',
        tree,
        re.MULTILINE,
    )
    return int(match.group(1), 16) if match else None


def close_kiosk():
    """Close only the visible kiosk window; its existing launcher restarts it."""
    tree = subprocess.check_output(["xwininfo", "-root", "-tree"], text=True, timeout=5)
    window = kiosk_window_id(tree)
    if window is None:
        return False
    x = ctypes.CDLL("libX11.so.6")
    xt = ctypes.CDLL("libXtst.so.6")
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XGetInputFocus.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
    ]
    x.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x.XStringToKeysym.restype = ctypes.c_ulong
    x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x.XKeysymToKeycode.restype = ctypes.c_uint
    x.XFlush.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xt.XTestFakeKeyEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_ulong,
    ]
    display = x.XOpenDisplay(None)
    if not display:
        return False
    try:
        focused = ctypes.c_ulong()
        revert = ctypes.c_int()
        x.XGetInputFocus(display, ctypes.byref(focused), ctypes.byref(revert))
        # Do not interrupt someone using another desktop application.
        if focused.value != window:
            return False
        keys = [
            x.XKeysymToKeycode(display, x.XStringToKeysym(k)) for k in [b"Alt_L", b"F4"]
        ]
        for key in keys:
            xt.XTestFakeKeyEvent(display, key, 1, 0)
        for key in reversed(keys):
            xt.XTestFakeKeyEvent(display, key, 0, 0)
        x.XFlush(display)
        return True
    finally:
        x.XCloseDisplay(display)


def main():
    """Monitor every 30 seconds without recycling during network outages."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    healthy_since = None
    last_restart = time.monotonic() - 600
    while True:
        now = time.monotonic()
        try:
            with urllib.request.urlopen(URL, timeout=8) as response:
                data = json.load(response)
            if "age_seconds" not in data:
                raise ValueError("Missing heartbeat age")
            if healthy_since is None:
                healthy_since = now
            if should_recover(
                data["age_seconds"], now - healthy_since, now - last_restart
            ):
                if close_kiosk():
                    logging.warning(
                        "Recovered kiosk with stale rendering heartbeat; age=%s",
                        data["age_seconds"],
                    )
                    last_restart = now
                    healthy_since = None
        except Exception as exc:
            healthy_since = None
            logging.info(
                "Health check unavailable; preserving kiosk: %s", type(exc).__name__
            )
        time.sleep(30)


if __name__ == "__main__":
    main()
