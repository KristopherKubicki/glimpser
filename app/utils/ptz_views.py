"""Serialized, opt-in preset stills with a verified return view."""

import hashlib
import io
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

from app import config
from app.utils import file_locks as fcntl


class Busy(RuntimeError):
    """The camera belongs to another capture or a manual operator."""


def root():
    """Return the private, persistent PTZ coordination directory."""
    path = Path(config.DATABASE_PATH).resolve().parent / "ptz_views"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings():
    """Read the explicit parent/preset allowlist; default to no automation."""
    try:
        return json.loads((root() / "config.json").read_text()).get("parents", {})
    except (OSError, ValueError, AttributeError):
        return {}


def _path(parent, suffix):
    return root() / (hashlib.sha256(parent.encode()).hexdigest() + suffix)


def _write(path, value):
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def owner(name):
    """Resolve only configured cameras and child views to their physical parent."""
    for parent, cfg in settings().items():
        if name == parent or name in cfg.get("views", {}):
            return parent, cfg
    return None, {}


def paused(parent):
    return float(_read(_path(parent, ".manual.json")).get("until", 0)) > time.time()


@contextmanager
def lock(parent, wait=0):
    """Coordinate independent scheduler processes and the web server."""
    with _path(parent, ".lock").open("a") as handle:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Busy("ptz_busy")
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def manual(name):
    """Cancel automatic work, then give the operator a 15-minute quiet period."""
    parent, _ = owner(name)
    if not parent:
        yield
        return
    _write(_path(parent, ".manual.json"), {"until": time.time() + 900})
    with lock(parent, wait=20):
        # Manual control takes ownership of the final view. Do not force home
        # over the operator after a cancelled automatic capture.
        _path(parent, ".return.json").unlink(missing_ok=True)
        yield


def _command(template, action, preset=None):
    from app.utils.camera_discovery import control_onvif_ptz

    result = control_onvif_ptz(
        template["url"],
        action=action,
        preset_token=preset,
        username=template.get("auth_username"),
        password=template.get("auth_password"),
        ptz_service=template.get("ptz_service"),
        profile_token=template.get("ptz_profile_token"),
        timeout=3,
    )
    if not result.get("ok"):
        raise RuntimeError("ptz_" + action + "_failed")


def snapshot(template):
    """Read and validate camera pixels through its existing private UID connector."""
    from app.utils.screenshots import _uid_cgi_snapshot_url, http_session

    url = _uid_cgi_snapshot_url(
        template["url"], template.get("auth_username"), template.get("auth_password"), 3
    )
    if not url:
        raise RuntimeError("ptz_snapshot_unavailable")
    response = http_session().get(url, timeout=(3, 5))
    try:
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as image:
            image.load()
            if min(image.size) < 200:
                raise RuntimeError("ptz_snapshot_too_small")
            return image.convert("RGB")
    finally:
        response.close()


def distance(left, right):
    """Compare the scene excluding timestamp bands, discounting global brightness."""

    def pixels(image):
        w, h = image.size
        return np.asarray(
            image.convert("L")
            .crop((w * 0.05, h * 0.12, w * 0.95, h * 0.88))
            .resize((96, 64)),
            dtype=float,
        )

    a, b = pixels(left), pixels(right)
    # Low-cost motors can land a few pixels away from a saved position. Allow
    # bounded registration, not a different composition or an unbounded crop.
    scores = []
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            delta = a[3:-3, 3:-3] - b[3 + dy : 61 + dy, 3 + dx : 93 + dx]
            scores.append(float(np.mean(np.abs(delta - np.median(delta)))))
    return min(scores)


def _settle(parent, seconds=4, interruptible=True):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if interruptible and paused(parent):
            raise Busy("ptz_manual_override")
        time.sleep(0.2)


def _home(parent, cfg, template):
    _command(template, "preset", cfg["home"])
    _settle(parent)
    _command(template, "stop")
    reference = _path(parent, ".home.png")
    if not reference.exists():
        raise RuntimeError("ptz_home_not_calibrated")
    with Image.open(reference) as image:
        if distance(image, snapshot(template)) > float(cfg.get("home_tolerance", 12)):
            raise RuntimeError("ptz_return_not_verified")
    _path(parent, ".return.json").unlink(missing_ok=True)


def capture(name, template, normal, provided):
    """Capture a named view only after restoring and verifying the parent view."""
    from app.utils.screenshots import CAPTURE_STALE_PREVIOUS
    from app.utils.template_manager import get_template

    parent, cfg = owner(name)
    if not parent:
        # Never let an unconfigured child fall through to a generic URL capture.
        if str(template.get("url", "")).startswith("ptzview:"):
            return CAPTURE_STALE_PREVIOUS
        return normal()
    try:
        with lock(parent):
            parent_template = template if name == parent else get_template(parent)
            pending = _path(parent, ".return.json")
            if pending.exists():
                if paused(parent) or _read(_path(parent, ".state.json")).get("fault"):
                    return CAPTURE_STALE_PREVIOUS
                _home(parent, cfg, parent_template)
            if name == parent:
                return normal()
            state_path = _path(parent, ".state.json")
            state = _read(state_path)
            if not cfg.get("enabled") or paused(parent) or state.get("fault"):
                return CAPTURE_STALE_PREVIOUS
            if time.time() - state.get(name, 0) < cfg.get("interval_seconds", 3600):
                return CAPTURE_STALE_PREVIOUS
            if not _path(parent, ".home.png").exists():
                return CAPTURE_STALE_PREVIOUS
            # Persist before movement so a killed worker leaves a recoverable
            # return obligation. Normal captures cannot save the wrong angle.
            _write(pending, {"view": name, "started": time.time()})
            frame = None
            try:
                _command(parent_template, "preset", str(cfg["views"][name]["preset"]))
                _settle(parent)
                _command(parent_template, "stop")
                first = snapshot(parent_template)
                _settle(parent, 1)
                frame = snapshot(parent_template)
                captured_at = time.time()
                if distance(first, frame) > 5:
                    raise RuntimeError("ptz_view_not_settled")
                reference = _path(
                    parent, "." + str(cfg["views"][name]["preset"]) + ".png"
                )
                with Image.open(reference) as image:
                    if distance(image, frame) > cfg.get("view_tolerance", 14):
                        raise RuntimeError("ptz_preset_not_verified")
            finally:
                try:
                    _command(parent_template, "stop")
                finally:
                    if not paused(parent):
                        _home(parent, cfg, parent_template)
            if paused(parent):
                return CAPTURE_STALE_PREVIOUS
            temporary = _path(parent, ".capture.png")
            try:
                frame.save(temporary)
                os.utime(temporary, (captured_at, captured_at))
                result = provided(str(temporary))
            finally:
                temporary.unlink(missing_ok=True)
            if result is True:
                state[name] = time.time()
                _write(state_path, state)
            return result
    except Busy:
        return CAPTURE_STALE_PREVIOUS
    except Exception as exc:
        # Do not expose camera URLs/credentials from transport exceptions.
        _write(
            _path(parent, ".state.json"),
            {"fault": type(exc).__name__, "at": time.time()},
        )
        return CAPTURE_STALE_PREVIOUS
