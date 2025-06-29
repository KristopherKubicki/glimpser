import ctypes
import ctypes.util
import logging
import os
import platform
import threading
import time

keyboard = None
mouse = None


def _safe_import_pynput() -> None:
    """Import pynput when input libraries are available."""
    global keyboard, mouse
    if keyboard is not None and mouse is not None:
        return
    display = os.environ.get("DISPLAY")
    system = platform.system()
    if display is None and system not in ("Darwin", "Windows"):
        logging.debug("Skipping pynput import: no DISPLAY set")
        return
    try:
        from pynput import keyboard as _keyboard
        from pynput import mouse as _mouse

        keyboard = _keyboard
        mouse = _mouse
    except Exception as e:  # pragma: no cover - optional dependency
        mouse = None
        keyboard = None
        logging.warning("pynput not available: %s", e)


_safe_import_pynput()

# Global flag to track user activity
user_active = False


# Callback functions to update activity state
def on_move(x, y):
    """Set ``user_active`` when the mouse moves.

    Args:
        x (int): The mouse X coordinate.
        y (int): The mouse Y coordinate.
    """

    global user_active
    user_active = True


def on_click(x, y, button, pressed):
    """Set ``user_active`` when a mouse button is clicked.

    Args:
        x (int): The mouse X coordinate.
        y (int): The mouse Y coordinate.
        button: The mouse button pressed.
        pressed (bool): Whether the button is pressed.
    """

    global user_active
    user_active = True


def on_scroll(x, y, dx, dy):
    """Set ``user_active`` when the mouse wheel scrolls.

    Args:
        x (int): The mouse X coordinate.
        y (int): The mouse Y coordinate.
        dx (int): Horizontal scroll delta.
        dy (int): Vertical scroll delta.
    """

    global user_active
    user_active = True


def on_press(key):
    """Set ``user_active`` when a key is pressed.

    Args:
        key: The pressed key.
    """

    global user_active
    user_active = True


_idle_lock = threading.Lock()
_x11 = None
_xss = None


class XScreenSaverInfo(ctypes.Structure):
    """Structure for XScreenSaverInfo returned by libXss."""

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
    """Return seconds of user idleness according to systemd-logind."""
    import subprocess

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
            timeout=0.3,
        ).splitlines()
    except subprocess.SubprocessError:
        raise RuntimeError("loginctl unavailable")
    props = dict(l.split("=", 1) for l in out if "=" in l)
    if props.get("IdleHint", "no") != "yes":
        return 0
    idle_us = int(props["IdleSinceHintMonotonicUSec"])
    return int((time.monotonic() * 1_000_000 - idle_us) / 1_000_000)


def idle_seconds_windows() -> int:
    """Return idle seconds on Windows systems."""
    import ctypes.wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.UINT),
            ("dwTime", ctypes.wintypes.DWORD),
        ]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise RuntimeError("GetLastInputInfo failed")
    millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis // 1000


def idle_seconds_macos() -> int:
    """Return idle seconds on macOS systems."""
    import subprocess

    try:
        out = subprocess.check_output(
            ["ioreg", "-c", "IOHIDSystem"], text=True, timeout=0.3
        )
    except subprocess.SubprocessError:
        raise RuntimeError("ioreg unavailable")
    for line in out.splitlines():
        if "HIDIdleTime" in line:
            nanoseconds = int(line.split()[-1])
            return nanoseconds // 1_000_000_000
    raise RuntimeError("HIDIdleTime not found")


def check_user_activity(timeout: int = 10) -> bool:
    """Return True if recent user interaction is observed.

    Args:
        timeout (int): Seconds to wait for an input event.

    Returns:
        bool: ``True`` if the user appears active.
    """

    _safe_import_pynput()
    global user_active
    user_active = False
    try:
        idle_seconds_x = idle_seconds_x11()
        if idle_seconds_x < 120:
            user_active = True
            return user_active
    except Exception as e:
        logging.debug(f"idle_seconds_x11 failed: {e}")
        try:
            idle_seconds_l = idle_seconds_loginctl()
            if idle_seconds_l < 120:
                user_active = True
                return user_active
        except Exception as e2:
            logging.debug(f"idle_seconds_loginctl failed: {e2}")
            system = platform.system()
            try:
                if system == "Windows":
                    idle_os = idle_seconds_windows()
                elif system == "Darwin":
                    idle_os = idle_seconds_macos()
                else:
                    idle_os = None
                if idle_os is not None and idle_os < 120:
                    user_active = True
                    return user_active
            except Exception as e3:
                logging.debug(f"idle_seconds_{system.lower()} failed: {e3}")
    if mouse is None or keyboard is None:
        return user_active
    mouse_listener = None
    keyboard_listener = None
    try:
        mouse_listener = mouse.Listener(
            on_move=on_move, on_click=on_click, on_scroll=on_scroll
        )
        keyboard_listener = keyboard.Listener(on_press=on_press)
        mouse_listener.start()
        keyboard_listener.start()
    except Exception as e:  # pragma: no cover - best effort
        logging.debug(f"pynput listener failed: {e}")
        if mouse_listener:
            try:
                mouse_listener.stop()
                mouse_listener.join()
            except Exception:
                pass
        if keyboard_listener:
            try:
                keyboard_listener.stop()
                keyboard_listener.join()
            except Exception:
                pass
        return user_active
    start_time = time.time()
    while time.time() - start_time < timeout:
        if user_active:
            break
        time.sleep(0.1)
    if mouse_listener:
        mouse_listener.stop()
    if keyboard_listener:
        keyboard_listener.stop()
    if mouse_listener:
        mouse_listener.join()
    if keyboard_listener:
        keyboard_listener.join()
    return user_active


def _send_input_event() -> None:
    """Move the mouse slightly to generate an input event."""
    _safe_import_pynput()
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
