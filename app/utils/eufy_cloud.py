"""Eufy cloud helpers.

Glimpser keeps Eufy cloud access enclosed by routing snapshot fetches through
local Glimpser endpoints. Templates can use stable URLs like:

    eufy://<profile>/<device_id>

At capture time those URLs are converted to signed local proxy URLs
(``/integrations/eufy/snapshot``), so camera credentials/tokens stay
server-side.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from itsdangerous import BadData, URLSafeSerializer

from app import config

_SNAPSHOT_TOKEN_SALT = "eufy-cloud-snapshot-v1"
_EUFY_DOMAIN_BASE = "https://extend.eufylife.com"
_EUFY_SERVER_PUBLIC_KEY = (
    "04c5c00c4f8d1197cc7c3167c52bf7acb054d722f0ef08dcd7e0883236e0d72a"
    "3868d9750cb47fa4619248f3d83f0f662671dadc6e2d31c2f41db0161651c7c076"
)
_EUFY_OPENUDID = "5e4621b0152c0d00"
_NATIVE_REFRESH_GRACE_SECONDS = 60.0
_EUFY_CAPTCHA_LENGTH = 4

_NATIVE_SESSION_LOCK = threading.Lock()
_NATIVE_SESSIONS: dict[str, dict[str, object]] = {}
_NATIVE_CAPTCHA_LOCK = threading.Lock()
_NATIVE_CAPTCHAS: dict[str, dict[str, object]] = {}
_NATIVE_CAPTCHA_OCR_LOCK = threading.Lock()
_NATIVE_CAPTCHA_OCR_ATTEMPTS: dict[tuple[str, str], float] = {}
_WEBPORTAL_CAPTURE_LOCKS: dict[str, threading.Lock] = {}
_WEBPORTAL_PIN_BACKOFF_UNTIL: dict[str, float] = {}
_WEBPORTAL_PIN_BACKOFF_SECONDS = 15 * 60
_EMULATOR_BOOT_LOCKS: dict[str, threading.Lock] = {}
_EMULATOR_BOOT_LAST_START: dict[str, float] = {}
_EUFY_EMULATOR_ONLY = True
_EUFY_EMULATOR_WEBPORTAL_FALLBACK = False

_NATIVE_DEFAULT_HEADERS = {
    "User-Agent": "EufySecurity/4.6.0_1630 (Android 12; ONEPLUS A3003)",
    "App_version": "v4.6.0_1630",
    "Os_type": "android",
    "Os_version": "31",
    "Phone_model": "ONEPLUS A3003",
    "Language": "en",
    "Net_type": "wifi",
    "Mnc": "02",
    "Mcc": "262",
    "Sn": "75814221ee75",
    "Model_type": "PHONE",
    "Cache-Control": "no-cache",
}


class EufyCloudError(RuntimeError):
    """Raised when Eufy cloud integration calls fail."""


class EufyCaptchaRequired(EufyCloudError):
    """Raised when Eufy cloud requires a human captcha challenge."""

    def __init__(
        self,
        profile: str,
        captcha_id: str,
        captcha_item: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.profile = str(profile or "default").strip().lower() or "default"
        self.captcha_id = str(captcha_id or "").strip()
        self.captcha_item = str(captcha_item or "").strip()


@dataclass(frozen=True)
class EufyCloudProfile:
    """Normalized Eufy integration profile."""

    name: str
    mode: str
    bridge_url: str
    api_token: str
    devices_path: str
    snapshot_path: str
    verify_tls: bool
    native_email: str
    native_password: str
    native_country: str
    webportal_url: str = ""
    webportal_pin: str = ""
    webportal_user_data_dir: str = ""
    emulator_adb_path: str = ""
    emulator_adb_serial: str = ""
    emulator_launch_cmd: str = ""
    emulator_capture_cmd: str = ""
    emulator_boot_cmd: str = ""
    emulator_boot_timeout_seconds: float = 45.0
    emulator_devices_json: str = ""
    emulator_settle_seconds: float = 2.0


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(str(config.SECRET_KEY), salt=_SNAPSHOT_TOKEN_SALT)


def _normalize_path(path: str, default: str) -> str:
    clean = str(path or "").strip() or default
    if not clean.startswith("/"):
        clean = "/" + clean
    return clean


def _join_url(base: str, path: str) -> str:
    return str(base).rstrip("/") + path


def _headers(profile: EufyCloudProfile) -> dict[str, str]:
    token = str(profile.api_token or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _parse_profiles_blob(raw: str) -> dict[str, dict]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        out[key] = value
    return out


def _load_profiles() -> dict[str, dict]:
    raw = config.get_setting("EUFY_CLOUD_PROFILES", "") or ""
    return _parse_profiles_blob(str(raw))


def list_profile_names() -> list[str]:
    payload = _load_profiles()
    names = sorted(n for n in payload.keys() if n and n != "default")
    return ["default", *names]


def resolve_profile(profile: str = "default") -> EufyCloudProfile | None:
    """Resolve a stored Eufy profile into normalized runtime settings."""

    payload = _load_profiles()
    key = str(profile or "default").strip().lower() or "default"
    value = payload.get(key)
    if not isinstance(value, dict):
        return None

    mode = str(value.get("mode") or "external").strip().lower()
    if mode == "native":
        # Native direct snapshot mode is deprecated; keep backward compatibility
        # by upgrading old profiles to webportal mode at runtime.
        mode = "webportal"
    if mode in {"vm", "webportal_vm"}:
        mode = "emulator"
    if mode not in {"external", "webportal", "emulator"}:
        mode = "external"
    if _EUFY_EMULATOR_ONLY and mode != "emulator":
        # Force emulator mode so no native/webportal cloud API paths run.
        mode = "emulator"

    bridge_url = str(value.get("bridge_url") or "").strip().rstrip("/")
    if mode == "external" and not bridge_url:
        return None

    devices_path = _normalize_path(value.get("devices_path") or "", "/api/devices")
    snapshot_path = _normalize_path(
        value.get("snapshot_path") or "", "/api/cameras/{device_id}/snapshot"
    )
    verify_tls = str(value.get("verify_tls", "true")).strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
        "y",
        "t",
    }
    webportal_url = str(
        value.get("webportal_url") or "https://mysecurity.eufylife.com/#/camera"
    ).strip()
    webportal_pin = str(value.get("webportal_pin") or "").strip()
    webportal_user_data_dir = str(value.get("webportal_user_data_dir") or "").strip()
    emulator_adb_path = str(value.get("emulator_adb_path") or "").strip()
    emulator_adb_serial = str(value.get("emulator_adb_serial") or "").strip()
    emulator_launch_cmd = str(value.get("emulator_launch_cmd") or "").strip()
    emulator_capture_cmd = str(value.get("emulator_capture_cmd") or "").strip()
    emulator_boot_cmd = str(value.get("emulator_boot_cmd") or "").strip()
    try:
        emulator_boot_timeout_seconds = float(
            value.get("emulator_boot_timeout_seconds") or 45.0
        )
    except Exception:
        emulator_boot_timeout_seconds = 45.0
    emulator_boot_timeout_seconds = max(5.0, min(emulator_boot_timeout_seconds, 240.0))
    emulator_devices_json = str(value.get("emulator_devices_json") or "").strip()
    try:
        emulator_settle_seconds = float(value.get("emulator_settle_seconds") or 2.0)
    except Exception:
        emulator_settle_seconds = 2.0
    emulator_settle_seconds = max(0.0, min(emulator_settle_seconds, 60.0))

    return EufyCloudProfile(
        name=key,
        mode=mode,
        bridge_url=bridge_url,
        api_token=str(value.get("api_token") or "").strip(),
        devices_path=devices_path,
        snapshot_path=snapshot_path,
        verify_tls=verify_tls,
        native_email=str(value.get("native_email") or "").strip(),
        native_password=str(value.get("native_password") or "").strip(),
        native_country=str(value.get("native_country") or "US").strip() or "US",
        webportal_url=webportal_url,
        webportal_pin=webportal_pin,
        webportal_user_data_dir=webportal_user_data_dir,
        emulator_adb_path=emulator_adb_path,
        emulator_adb_serial=emulator_adb_serial,
        emulator_launch_cmd=emulator_launch_cmd,
        emulator_capture_cmd=emulator_capture_cmd,
        emulator_boot_cmd=emulator_boot_cmd,
        emulator_boot_timeout_seconds=emulator_boot_timeout_seconds,
        emulator_devices_json=emulator_devices_json,
        emulator_settle_seconds=emulator_settle_seconds,
    )


def configured(profile: str = "default") -> bool:
    """Return whether a profile has enough config to capture snapshots."""

    prof = resolve_profile(profile)
    if prof is None:
        return False
    if prof.mode == "webportal":
        return bool(prof.webportal_url and prof.native_email and prof.native_password)
    if prof.mode == "emulator":
        return bool(str(prof.emulator_devices_json or "").strip())
    return bool(prof.bridge_url)


def parse_eufy_url(url: str) -> tuple[str, str]:
    """Parse ``eufy://`` URLs into ``(profile, device_id)``."""

    parsed = urlparse(str(url or ""))
    if parsed.scheme.lower() != "eufy":
        return "", ""

    profile = (parsed.hostname or "").strip().lower() or "default"
    device_id = parsed.path.lstrip("/")

    # Support compact form `eufy://<device_id>` for the default profile.
    if not device_id and parsed.netloc and not parsed.path:
        profile = "default"
        device_id = parsed.netloc.strip()

    return profile, device_id.strip()


def issue_snapshot_token(profile: str, device_id: str) -> str:
    payload = {"p": str(profile or "default").strip() or "default", "d": str(device_id)}
    return str(_serializer().dumps(payload))


def verify_snapshot_token(token: str) -> tuple[str, str] | None:
    token = str(token or "").strip()
    if not token:
        return None
    try:
        data = _serializer().loads(token)
    except BadData:
        return None
    if not isinstance(data, dict):
        return None
    profile = str(data.get("p") or "default").strip() or "default"
    device_id = str(data.get("d") or "").strip()
    if not device_id:
        return None
    return profile, device_id


def build_snapshot_proxy_url(profile: str, device_id: str) -> str:
    if bool(getattr(config, "HTTPS_ENABLED", False)) and bool(
        getattr(config, "HTTPS_ONLY", False)
    ):
        scheme = "https"
        port = int(getattr(config, "HTTPS_PORT", 8443))
    else:
        scheme = "http"
        port = int(getattr(config, "PORT", 8082))

    profile = str(profile or "default").strip().lower() or "default"
    device_id = str(device_id or "").strip()
    token = issue_snapshot_token(profile, device_id)
    return (
        f"{scheme}://127.0.0.1:{port}/integrations/eufy/snapshot"
        f"?profile={quote(profile, safe='')}"
        f"&device_id={quote(device_id, safe='')}"
        f"&token={quote(token, safe='')}"
    )


def resolve_eufy_to_snapshot(url: str) -> str:
    profile, device_id = parse_eufy_url(url)
    if not device_id:
        raise EufyCloudError("Invalid Eufy URL: missing device id")
    if not configured(profile):
        raise EufyCloudError(f"Eufy cloud profile '{profile}' is not configured")
    return build_snapshot_proxy_url(profile, device_id)


def ensure_bridge_running(profile: str = "default") -> None:
    """Compatibility no-op kept for legacy call sites."""

    _ = profile


def _extract_devices(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("devices", "cameras", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _emulator_device_entries(profile: EufyCloudProfile) -> list[dict]:
    """Parse emulator device catalog JSON into normalized camera entries."""

    raw = str(profile.emulator_devices_json or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise EufyCloudError(
            f"Invalid emulator device catalog JSON for profile '{profile.name}': {exc}"
        ) from exc

    out: list[dict] = []
    for item in _extract_devices(payload):
        did = str(
            item.get("device_id")
            or item.get("id")
            or item.get("serialNumber")
            or item.get("serial")
            or ""
        ).strip()
        if not did:
            continue
        out.append(
            {
                "device_id": did,
                "name": str(
                    item.get("name") or item.get("label") or item.get("nickname") or did
                ).strip(),
                "online": bool(item.get("online", True)),
                "snapshot": bool(item.get("snapshot", True)),
                "model": str(item.get("model") or "").strip(),
                "station": str(
                    item.get("station") or item.get("homebase") or ""
                ).strip(),
                "deep_link": str(
                    item.get("deep_link")
                    or item.get("deeplink")
                    or item.get("url")
                    or ""
                ).strip(),
                "launch_cmd": str(item.get("launch_cmd") or "").strip(),
                "capture_cmd": str(item.get("capture_cmd") or "").strip(),
            }
        )
    out.sort(key=lambda row: str(row.get("name") or "").lower())
    return out


def _emulator_apply_template(
    value: str, *, profile: str, device: dict[str, object]
) -> str:
    text = str(value or "")
    return (
        text.replace("{profile}", str(profile))
        .replace("{device_id}", str(device.get("device_id") or ""))
        .replace("{device_name}", str(device.get("name") or ""))
        .replace("{deep_link}", str(device.get("deep_link") or ""))
    )


def _emulator_run_command(
    cmd: str | list[str],
    *,
    timeout: float,
    profile: str,
    device: dict[str, object],
) -> subprocess.CompletedProcess[bytes]:
    if isinstance(cmd, str):
        rendered = _emulator_apply_template(cmd, profile=profile, device=device)
        args = shlex.split(rendered)
    else:
        args = [str(part) for part in cmd if str(part)]
    if not args:
        raise EufyCloudError("Emulator command is empty.")
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=max(1.0, float(timeout)),
        )
    except FileNotFoundError as exc:
        raise EufyCloudError(f"Emulator command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise EufyCloudError(f"Emulator command timed out: {' '.join(args)}") from exc
    except Exception as exc:
        raise EufyCloudError(
            f"Emulator command failed to execute: {' '.join(args)} ({exc})"
        ) from exc


def _emulator_adb_prefix(profile: EufyCloudProfile) -> list[str]:
    adb_bin = str(profile.emulator_adb_path or "").strip()
    if not adb_bin:
        adb_bin = str(os.getenv("GLIMPSER_EUFY_ADB_PATH") or "").strip()
    if not adb_bin:
        adb_bin = shutil.which("adb") or ""
    if not adb_bin:
        local_candidates = (
            Path(__file__).resolve().parents[2] / "bin" / "adb",
            Path(config.DATABASE_PATH).resolve().parent
            / "tools"
            / "platform-tools"
            / "adb",
        )
        for candidate in local_candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                adb_bin = str(candidate)
                break
    if not adb_bin:
        raise EufyCloudError(
            "ADB executable not found. Install Android platform-tools, set "
            "GLIMPSER_EUFY_ADB_PATH, or set Emulator ADB Path in /integrations/eufy."
        )

    prefix = [adb_bin]
    serial = str(profile.emulator_adb_serial or "").strip()
    if serial:
        prefix.extend(["-s", serial])
    return prefix


def _emulator_boot_lock(profile_name: str) -> threading.Lock:
    key = str(profile_name or "default").strip().lower() or "default"
    lock = _EMULATOR_BOOT_LOCKS.get(key)
    if lock is None:
        lock = threading.Lock()
        _EMULATOR_BOOT_LOCKS[key] = lock
    return lock


def _emulator_guess_boot_cmd(profile: EufyCloudProfile) -> str:
    """Best-effort boot command discovery when profile boot command is empty."""

    env_cmd = str(os.getenv("GLIMPSER_EUFY_BOOT_CMD") or "").strip()
    if env_cmd:
        return env_cmd

    virsh_bin = shutil.which("virsh") or ""
    if virsh_bin:
        try:
            result = subprocess.run(
                [virsh_bin, "list", "--all", "--name"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=2.0,
            )
        except Exception:
            result = None
        if result and result.returncode == 0:
            names = [
                item.strip()
                for item in (result.stdout or b"")
                .decode("utf-8", "ignore")
                .splitlines()
                if item.strip()
            ]
            if names:
                wanted = next(
                    (
                        item
                        for item in names
                        if re.search(
                            r"(eufy|android|emulator|glimpser|avd)", item, re.I
                        )
                    ),
                    names[0],
                )
                return f"{shlex.quote(virsh_bin)} start {shlex.quote(wanted)}"

    waydroid_bin = shutil.which("waydroid") or ""
    if waydroid_bin:
        return f"{shlex.quote(waydroid_bin)} session start"

    emulator_candidates: list[str] = []
    from_path = shutil.which("emulator") or ""
    if from_path:
        emulator_candidates.append(from_path)
    for root in (
        os.getenv("ANDROID_SDK_ROOT", ""),
        os.getenv("ANDROID_HOME", ""),
        str(Path.home() / "Android" / "Sdk"),
        str(Path.home() / "Android" / "sdk"),
    ):
        root = str(root or "").strip()
        if not root:
            continue
        candidate = str(Path(root) / "emulator" / "emulator")
        if candidate not in emulator_candidates:
            emulator_candidates.append(candidate)

    for emulator_bin in emulator_candidates:
        path = Path(emulator_bin)
        if not path.exists() or not os.access(path, os.X_OK):
            continue
        try:
            result = subprocess.run(
                [str(path), "-list-avds"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=2.0,
            )
        except Exception:
            continue
        if result.returncode != 0:
            continue
        avds = [
            item.strip()
            for item in (result.stdout or b"").decode("utf-8", "ignore").splitlines()
            if item.strip()
        ]
        if not avds:
            continue
        wanted = next(
            (
                item
                for item in avds
                if re.search(r"(eufy|android|emulator|glimpser|avd)", item, re.I)
            ),
            avds[0],
        )
        return (
            f"{shlex.quote(str(path))} -avd {shlex.quote(wanted)} "
            "-no-snapshot-load -no-boot-anim -no-window"
        )

    return ""


def _emulator_adb_ready(profile: EufyCloudProfile) -> bool:
    try:
        result = _emulator_run_command(
            _emulator_adb_prefix(profile) + ["get-state"],
            timeout=2.0,
            profile=profile.name,
            device={},
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    state = (result.stdout or b"").decode("utf-8", "ignore").strip().lower()
    return state == "device"


def _emulator_try_adb_connect(profile: EufyCloudProfile) -> bool:
    """Attempt `adb connect` for TCP targets when serial uses host:port."""

    targets: list[str] = []
    serial = str(profile.emulator_adb_serial or "").strip()
    if ":" in serial and not serial.lower().startswith("emulator-"):
        targets.append(serial)

    env_targets = str(os.getenv("GLIMPSER_EUFY_ADB_TARGETS") or "").strip()
    if env_targets:
        for raw in env_targets.split(","):
            target = raw.strip()
            if target:
                targets.append(target)

    # Last-resort local default for common emulator TCP ADB setups.
    if not targets:
        targets.append("127.0.0.1:5555")

    seen: set[str] = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        try:
            _emulator_run_command(
                [str(_emulator_adb_prefix(profile)[0]), "connect", target],
                timeout=3.0,
                profile=profile.name,
                device={},
            )
        except Exception:
            continue
        if _emulator_adb_ready(profile):
            return True
    return False


def _emulator_ensure_ready(profile: EufyCloudProfile, *, timeout: float) -> None:
    """Ensure one ADB target is ready before screenshot capture.

    This keeps lifecycle handling inside Glimpser: start ADB, optionally launch
    the VM/emulator with a profile boot command, then wait for `adb get-state`
    to report `device`.
    """

    if _emulator_adb_ready(profile):
        return

    # Start the server first; this is cheap and fixes stale daemon state.
    try:
        _emulator_run_command(
            _emulator_adb_prefix(profile) + ["start-server"],
            timeout=3.0,
            profile=profile.name,
            device={},
        )
    except Exception:
        pass

    if _emulator_adb_ready(profile):
        return
    if _emulator_try_adb_connect(profile):
        return

    boot_cmd = str(profile.emulator_boot_cmd or "").strip()
    if not boot_cmd:
        boot_cmd = _emulator_guess_boot_cmd(profile)
    if not boot_cmd:
        raise EufyCloudError(
            "No emulator/device available via ADB and no boot strategy could be "
            "auto-detected. Set Emulator Boot Command in /integrations/eufy."
        )

    lock = _emulator_boot_lock(profile.name)
    with lock:
        if _emulator_adb_ready(profile):
            return

        last_start = float(_EMULATOR_BOOT_LAST_START.get(profile.name) or 0.0)
        now = time.monotonic()
        # Avoid thundering-herd restarts when multiple cameras capture at once.
        if now - last_start > 10.0:
            result = _emulator_run_command(
                boot_cmd,
                timeout=min(max(timeout, 5.0), 30.0),
                profile=profile.name,
                device={},
            )
            _EMULATOR_BOOT_LAST_START[profile.name] = time.monotonic()
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", "ignore").strip()
                raise EufyCloudError(
                    f"Emulator boot command failed (exit={result.returncode}): "
                    f"{err or boot_cmd}"
                )

        deadline = time.monotonic() + min(
            max(float(profile.emulator_boot_timeout_seconds or 45.0), 5.0), 240.0
        )
        while time.monotonic() < deadline:
            if _emulator_adb_ready(profile):
                return
            time.sleep(1.0)

    raise EufyCloudError(
        "ADB target did not become ready in time after boot command. "
        "Check emulator VM health and ADB serial."
    )


def _emulator_fallback_to_webportal(
    profile: EufyCloudProfile,
    device_id: str,
    *,
    timeout: float,
    reason: str,
) -> tuple[bytes, str] | None:
    """Fallback to web portal capture when local emulator tooling is unavailable."""

    if not _EUFY_EMULATOR_WEBPORTAL_FALLBACK:
        return None

    lowered = str(reason or "").lower()
    retryable = (
        "adb executable not found",
        "command not found",
        "no devices/emulators found",
        "no emulator/device available via adb",
        "no boot strategy could be auto-detected",
        "device offline",
        "adb target did not become ready in time",
    )
    if not any(token in lowered for token in retryable):
        return None
    if not profile.webportal_url:
        return None
    if not profile.native_email or not profile.native_password:
        return None
    return _webportal_fetch_snapshot(profile, device_id, timeout=timeout)


def _emulator_pick_device(
    profile: EufyCloudProfile, device_id: str
) -> dict[str, object]:
    wanted = str(device_id or "").strip()
    for item in _emulator_device_entries(profile):
        if str(item.get("device_id") or "").strip() == wanted:
            return item
    raise EufyCloudError(
        f"Emulator profile '{profile.name}' does not define device '{wanted}'."
    )


def _emulator_open_device(
    profile: EufyCloudProfile, device: dict[str, object], *, timeout: float
) -> None:
    launch_cmd = str(
        device.get("launch_cmd") or profile.emulator_launch_cmd or ""
    ).strip()
    if launch_cmd:
        result = _emulator_run_command(
            launch_cmd,
            timeout=min(max(timeout, 1.0), 15.0),
            profile=profile.name,
            device=device,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", "ignore").strip()
            raise EufyCloudError(
                f"Emulator launch command failed (exit={result.returncode}): {err or launch_cmd}"
            )
        return

    deep_link = str(device.get("deep_link") or "").strip()
    if not deep_link:
        return
    cmd = _emulator_adb_prefix(profile) + [
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        deep_link,
    ]
    result = _emulator_run_command(
        cmd,
        timeout=min(max(timeout, 1.0), 15.0),
        profile=profile.name,
        device=device,
    )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", "ignore").strip()
        raise EufyCloudError(
            f"ADB deep-link launch failed (exit={result.returncode}): {err or deep_link}"
        )


def _emulator_capture_raw(
    profile: EufyCloudProfile,
    device: dict[str, object],
    *,
    timeout: float,
) -> bytes:
    capture_cmd = str(
        device.get("capture_cmd") or profile.emulator_capture_cmd or ""
    ).strip()
    if capture_cmd:
        result = _emulator_run_command(
            capture_cmd,
            timeout=max(timeout, 1.0),
            profile=profile.name,
            device=device,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", "ignore").strip()
            raise EufyCloudError(
                f"Emulator capture command failed (exit={result.returncode}): {err or capture_cmd}"
            )
        payload = bytes(result.stdout or b"")
    else:
        cmd = _emulator_adb_prefix(profile) + ["exec-out", "screencap", "-p"]
        result = _emulator_run_command(
            cmd,
            timeout=max(timeout, 1.0),
            profile=profile.name,
            device=device,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", "ignore").strip()
            raise EufyCloudError(
                f"ADB screencap failed (exit={result.returncode}): {err or 'unknown error'}"
            )
        payload = bytes(result.stdout or b"")

    payload = payload.replace(b"\r\n", b"\n")
    if not payload:
        raise EufyCloudError("Emulator capture returned empty output.")
    return payload


def _emulator_fetch_snapshot(
    profile: EufyCloudProfile,
    device_id: str,
    *,
    timeout: float,
) -> tuple[bytes, str]:
    """Capture one frame from an Android emulator/VM session."""
    try:
        _emulator_ensure_ready(profile, timeout=timeout)
        device = _emulator_pick_device(profile, device_id)
        _emulator_open_device(profile, device, timeout=timeout)
        settle = max(0.0, min(float(profile.emulator_settle_seconds or 0.0), 60.0))
        if settle > 0:
            time.sleep(min(settle, max(0.0, timeout - 0.2)))

        payload = _emulator_capture_raw(profile, device, timeout=timeout)
        if payload.startswith(b"\x89PNG"):
            return payload, "image/png"
        if payload.startswith(b"\xff\xd8"):
            return payload, "image/jpeg"
        if payload.startswith(b"RIFF") and b"WEBP" in payload[:32]:
            return payload, "image/webp"

        # Some commands emit image files in unusual encodings. Re-encode with
        # Pillow for compatibility with downstream capture/storage logic.
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as image:
            with io.BytesIO() as buf:
                image.convert("RGB").save(buf, "PNG")
                return buf.getvalue(), "image/png"
    except Exception as exc:
        fallback = _emulator_fallback_to_webportal(
            profile,
            device_id,
            timeout=timeout,
            reason=str(exc),
        )
        if fallback is not None:
            return fallback
        if isinstance(exc, EufyCloudError):
            raise exc
        raise EufyCloudError(
            "Emulator capture did not return a valid image payload."
        ) from exc


def _native_error_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return "unknown error"
    return str(
        payload.get("msg")
        or payload.get("message")
        or payload.get("error")
        or payload.get("reason")
        or "unknown error"
    ).strip()


def _native_error_code(payload: object) -> int:
    if not isinstance(payload, dict):
        return -1
    try:
        return int(payload.get("code", -1))
    except Exception:
        return -1


def _clear_native_session(profile_name: str) -> None:
    with _NATIVE_SESSION_LOCK:
        _NATIVE_SESSIONS.pop(profile_name, None)


def _set_native_captcha(profile_name: str, captcha_id: str, captcha_item: str) -> None:
    key = str(profile_name or "default").strip().lower() or "default"
    with _NATIVE_CAPTCHA_LOCK:
        _NATIVE_CAPTCHAS[key] = {
            "captcha_id": str(captcha_id or "").strip(),
            "captcha_item": str(captcha_item or "").strip(),
            "updated_at": time.time(),
        }


def get_native_captcha(profile: str = "default") -> dict[str, str] | None:
    """Return pending captcha challenge info for a profile, if any."""

    key = str(profile or "default").strip().lower() or "default"
    with _NATIVE_CAPTCHA_LOCK:
        raw = _NATIVE_CAPTCHAS.get(key)
    if not isinstance(raw, dict):
        return None
    captcha_id = str(raw.get("captcha_id") or "").strip()
    captcha_item = str(raw.get("captcha_item") or "").strip()
    if not captcha_id or not captcha_item:
        return None
    return {"captcha_id": captcha_id, "captcha_item": captcha_item}


def clear_native_captcha(profile: str = "default") -> None:
    """Clear pending captcha state for a profile."""

    key = str(profile or "default").strip().lower() or "default"
    with _NATIVE_CAPTCHA_LOCK:
        challenge = _NATIVE_CAPTCHAS.pop(key, None)
    if isinstance(challenge, dict):
        captcha_id = str(challenge.get("captcha_id") or "").strip()
        if captcha_id:
            with _NATIVE_CAPTCHA_OCR_LOCK:
                _NATIVE_CAPTCHA_OCR_ATTEMPTS.pop((key, captcha_id), None)


def _native_mark_captcha_ocr_attempt(profile: str, captcha_id: str) -> None:
    key = str(profile or "default").strip().lower() or "default"
    cid = str(captcha_id or "").strip()
    if not cid:
        return
    with _NATIVE_CAPTCHA_OCR_LOCK:
        _NATIVE_CAPTCHA_OCR_ATTEMPTS[(key, cid)] = time.time()


def _native_captcha_ocr_attempted(profile: str, captcha_id: str) -> bool:
    key = str(profile or "default").strip().lower() or "default"
    cid = str(captcha_id or "").strip()
    if not cid:
        return False
    with _NATIVE_CAPTCHA_OCR_LOCK:
        return (key, cid) in _NATIVE_CAPTCHA_OCR_ATTEMPTS


def _native_decode_captcha_item(captcha_item: str) -> bytes:
    data_url = str(captcha_item or "").strip()
    if not data_url:
        return b""
    if data_url.startswith("data:image"):
        try:
            encoded = data_url.split(",", 1)[1]
            return base64.b64decode(encoded)
        except Exception:
            return b""
    if data_url.startswith(("http://", "https://")):
        try:
            resp = requests.get(data_url, timeout=6)
        except Exception:
            return b""
        if resp.status_code >= 400:
            return b""
        content_type = str(resp.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("image/"):
            return b""
        return resp.content or b""
    return b""


def _native_extract_ocr_codes(raw: str, *, length: int | None = None) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    pieces = re.findall(r"[A-Za-z0-9]+", text)
    candidates: list[str] = []
    seen: set[str] = set()
    target_len = int(length) if length else None
    if target_len is not None and target_len < 1:
        target_len = None

    def _add_candidate(value: str) -> None:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", value)
        if not cleaned:
            return
        if cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)
        lower = cleaned.lower()
        if lower not in seen:
            seen.add(lower)
            candidates.append(lower)
        upper = cleaned.upper()
        if upper not in seen:
            seen.add(upper)
            candidates.append(upper)

    for piece in pieces:
        if not piece:
            continue
        if target_len is None:
            if len(piece) < 4:
                continue
            _add_candidate(piece)
            continue

        if len(piece) < target_len:
            continue
        if len(piece) == target_len:
            _add_candidate(piece)
            continue

        # When OCR returns extra noise, keep a small sliding window of candidates.
        window_count = min(len(piece) - target_len + 1, 8)
        for idx in range(window_count):
            _add_candidate(piece[idx : idx + target_len])
    return candidates


def _native_expand_ocr_ambiguities(
    codes: list[str], *, length: int | None = None, limit: int = 96
) -> list[str]:
    """Expand OCR candidates with common captcha ambiguities.

    Captchas frequently confuse similar glyphs (0/O, 1/l/I, 5/S, etc). Keep
    the search bounded and deterministic so login loops stay fast.
    """

    ambiguous = {
        "0": ("O", "o"),
        "O": ("0", "o"),
        "o": ("0", "O"),
        "1": ("I", "l"),
        "I": ("1", "l"),
        "l": ("1", "I"),
        "5": ("S", "s"),
        "S": ("5", "s"),
        "s": ("5", "S"),
        "2": ("Z", "z"),
        "Z": ("2", "z"),
        "z": ("2", "Z"),
        "8": ("B", "b"),
        "B": ("8", "b"),
        "b": ("8", "B"),
        "6": ("G", "g"),
        "G": ("6", "g"),
        "g": ("6", "G"),
    }
    wanted = int(length) if length else None
    if wanted is not None and wanted < 1:
        wanted = None

    expanded: list[str] = []
    seen: set[str] = set()

    def _push(code: str) -> None:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", str(code or ""))
        if wanted is not None and len(cleaned) != wanted:
            return
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        expanded.append(cleaned)

    for base in codes:
        _push(base)
        if len(expanded) >= limit:
            break
        queue = [base]
        local_seen = {base}
        # Bound each base candidate so we do not explode combinations.
        while queue and len(expanded) < limit and len(local_seen) < 24:
            current = queue.pop(0)
            for idx, ch in enumerate(current):
                swaps = ambiguous.get(ch, ())
                for replacement in swaps:
                    candidate = f"{current[:idx]}{replacement}{current[idx + 1 :]}"
                    if candidate in local_seen:
                        continue
                    local_seen.add(candidate)
                    queue.append(candidate)
                    _push(candidate)
                    if len(expanded) >= limit:
                        break
                if len(expanded) >= limit:
                    break
    return expanded


def _native_ollama_codes(image_bytes: bytes, *, timeout: float) -> list[str]:
    if not image_bytes:
        return []

    # Build a small set of image variants so OCR can recover from noisy
    # captcha backgrounds without running continuously in the scheduler.
    variants = [image_bytes]
    try:
        from PIL import Image, ImageFilter, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as img:
            upscaled = img.resize(
                (max(1, img.width * 4), max(1, img.height * 4)),
                Image.Resampling.LANCZOS,
            )
            gray = ImageOps.grayscale(img)
            contrast = ImageOps.autocontrast(gray)
            bw = contrast.point(lambda value: 255 if value > 140 else 0)
            sharp = contrast.filter(ImageFilter.SHARPEN)
            up_gray = ImageOps.grayscale(upscaled)
            up_contrast = ImageOps.autocontrast(up_gray)
            up_bw = up_contrast.point(lambda value: 255 if value > 150 else 0)
            for variant in (contrast, sharp, bw, up_contrast, up_bw):
                buf = io.BytesIO()
                variant.save(buf, format="PNG")
                variants.append(buf.getvalue())
    except Exception:
        # OCR still works with the original image when PIL/pre-processing fails.
        pass

    codes: list[str] = []
    seen: set[str] = set()
    model = str(getattr(config, "LOCAL_LLM_VISION_MODEL", "") or "").strip()
    if model:
        from app.utils.local_llm import ocr_with_ollama

        system_prompt = (
            "You are an OCR engine for captcha images. "
            f"Return only the {_EUFY_CAPTCHA_LENGTH}-character alphanumeric code. "
            "If the code is unreadable, return an empty response."
        )
        user_prompt = (
            f"Read the captcha text and return exactly {_EUFY_CAPTCHA_LENGTH} characters. "
            "If unsure, return nothing."
        )
        run_timeout = max(
            2.0, min(float(timeout or config.LOCAL_LLM_TIMEOUT_SECONDS), 180.0)
        )
        for payload in variants:
            text = ocr_with_ollama(
                model=model,
                system_prompt=system_prompt,
                prompt=user_prompt,
                image_bytes=payload,
                max_size=768,
                timeout=int(run_timeout),
                options={"temperature": 0, "num_predict": 8},
            )
            if not text:
                continue
            for code in _native_extract_ocr_codes(text, length=_EUFY_CAPTCHA_LENGTH):
                if code not in seen:
                    seen.add(code)
                    codes.append(code)
            if codes:
                break

    if codes:
        return _native_expand_ocr_ambiguities(
            codes, length=_EUFY_CAPTCHA_LENGTH, limit=96
        )

    # Keep a deterministic fallback when local vision models are unavailable
    # or overloaded: try system tesseract on the same image variants.
    tesseract_bin = shutil.which("tesseract")
    if not tesseract_bin:
        return []
    run_timeout = max(1.0, min(float(timeout or 8.0), 12.0))
    for payload in variants:
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                prefix="eufy_captcha_", suffix=".png", delete=False
            ) as tmp:
                tmp.write(payload)
                tmp_path = tmp.name
            for psm in ("8", "7", "10"):
                proc = subprocess.run(
                    [
                        tesseract_bin,
                        tmp_path,
                        "stdout",
                        "--psm",
                        psm,
                        "-c",
                        "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=run_timeout,
                    check=False,
                )
                if proc.returncode not in {0, 1}:
                    continue
                text = str(proc.stdout or "").strip()
                if not text:
                    continue
                for code in _native_extract_ocr_codes(
                    text, length=_EUFY_CAPTCHA_LENGTH
                ):
                    if code not in seen:
                        seen.add(code)
                        codes.append(code)
                if codes:
                    return _native_expand_ocr_ambiguities(
                        codes, length=_EUFY_CAPTCHA_LENGTH, limit=96
                    )
        except Exception:
            continue
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    return codes


def auto_solve_native_captcha(
    profile: str = "default",
    *,
    timeout: float = 10.0,
    force: bool = False,
) -> dict[str, object]:
    """Attempt OCR-based solving for a pending native Eufy captcha."""

    key = str(profile or "default").strip().lower() or "default"
    prof = resolve_profile(key)
    if not prof:
        return {"attempted": False, "solved": False, "reason": "profile_not_configured"}
    if prof.mode not in {"native", "webportal"}:
        return {
            "attempted": False,
            "solved": False,
            "reason": "profile_not_native_or_webportal",
        }

    challenge = get_native_captcha(key)
    if not challenge:
        return {"attempted": False, "solved": False, "reason": "no_pending_captcha"}

    captcha_id = str(challenge.get("captcha_id") or "").strip()
    if captcha_id and not force and _native_captcha_ocr_attempted(key, captcha_id):
        return {
            "attempted": False,
            "solved": False,
            "reason": "already_attempted_for_challenge",
            "captcha_id": captcha_id,
        }

    if captcha_id:
        _native_mark_captcha_ocr_attempt(key, captcha_id)

    image_bytes = _native_decode_captcha_item(challenge.get("captcha_item") or "")
    if not image_bytes:
        return {
            "attempted": True,
            "solved": False,
            "reason": "captcha_image_decode_failed",
            "captcha_id": captcha_id,
        }

    candidates = _native_ollama_codes(image_bytes, timeout=timeout)
    if not candidates:
        return {
            "attempted": True,
            "solved": False,
            "reason": "ocr_no_candidates",
            "captcha_id": captcha_id,
        }

    last_error = ""
    for code in candidates:
        try:
            submit_native_captcha(key, code, timeout=timeout)
            return {
                "attempted": True,
                "solved": True,
                "code": code,
                "captcha_id": captcha_id,
            }
        except EufyCaptchaRequired:
            last_error = "captcha_incorrect"
            continue
        except Exception as exc:
            last_error = str(exc)
            continue

    return {
        "attempted": True,
        "solved": False,
        "reason": last_error or "ocr_candidates_rejected",
        "captcha_id": captcha_id,
    }


def solve_cloud_captcha(
    profile: str = "default",
    *,
    timeout: float = 12.0,
    max_rounds: int = 3,
) -> dict[str, object]:
    """Request+solve Eufy cloud captcha with bounded retries.

    This runs the OCR solver and, when no pending challenge exists yet, forces
    a challenge refresh through the cloud API before trying again.
    """

    key = str(profile or "default").strip().lower() or "default"
    rounds = max(1, min(int(max_rounds or 1), 6))
    last_reason = "not_solved"

    for _ in range(rounds):
        result = auto_solve_native_captcha(key, timeout=timeout, force=True)
        if result.get("solved"):
            return result
        last_reason = str(result.get("reason") or "not_solved")

        prof = resolve_profile(key)
        if not prof or prof.mode not in {"native", "webportal"}:
            break

        # Refresh challenge state from cloud API before next OCR attempt.
        try:
            _native_list_devices(prof, timeout=timeout)
        except EufyCaptchaRequired:
            continue
        except Exception as exc:
            last_reason = f"challenge_refresh_failed:{exc}"
            break

    return {
        "attempted": True,
        "solved": False,
        "reason": last_reason,
    }


def _native_raise_captcha_required(
    profile: EufyCloudProfile,
    payload: object,
    code: int,
    msg: str,
) -> None:
    data = payload.get("data") if isinstance(payload, dict) else None
    captcha_id = str(data.get("captcha_id") if isinstance(data, dict) else "").strip()
    captcha_item = str(data.get("item") if isinstance(data, dict) else "").strip()
    if captcha_id and captcha_item:
        _set_native_captcha(profile.name, captcha_id, captcha_item)
        raise EufyCaptchaRequired(
            profile=profile.name,
            captcha_id=captcha_id,
            captcha_item=captcha_item,
            message=f"Eufy captcha required ({code}): {msg}",
        )


def _native_timezone_ms() -> int:
    """Return timezone offset in Eufy's expected millisecond format."""

    offset_minutes = int(time.localtime().tm_gmtoff / 60)
    return offset_minutes * 60 * 1000


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size or pad_len > len(data):
        raise EufyCloudError("Invalid Eufy API padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise EufyCloudError("Invalid Eufy API padding bytes")
    return data[:-pad_len]


def _native_encrypt_password(password: str, key: bytes) -> str:
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    payload = _pkcs7_pad(password.encode("utf-8"))
    return base64.b64encode(enc.update(payload) + enc.finalize()).decode("ascii")


def _native_decrypt_payload(data: str, key: bytes) -> object:
    iv = key[:16]
    raw = base64.b64decode(str(data or ""))
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    payload = dec.update(raw) + dec.finalize()
    unpadded = _pkcs7_unpad(payload)
    try:
        return json.loads(unpadded.decode("utf-8"))
    except Exception as exc:
        raise EufyCloudError("Failed to parse Eufy encrypted payload") from exc


def _native_headers(country: str) -> dict[str, str]:
    headers = dict(_NATIVE_DEFAULT_HEADERS)
    headers["Country"] = country.upper()
    headers["Timezone"] = time.strftime("GMT%z")
    headers["Openudid"] = _EUFY_OPENUDID
    return headers


def _native_api_base(
    country: str,
    *,
    timeout: float,
    verify_tls: bool,
) -> str:
    lookup_country = str(country or "US").strip().upper() or "US"
    try:
        resp = requests.get(
            f"{_EUFY_DOMAIN_BASE}/domain/{lookup_country}",
            timeout=timeout,
            verify=verify_tls,
        )
    except Exception as exc:
        raise EufyCloudError(f"Eufy domain lookup failed: {exc}") from exc

    if resp.status_code >= 400:
        body = (resp.text or "").strip().replace("\n", " ")[:120]
        raise EufyCloudError(
            f"Eufy domain lookup returned HTTP {resp.status_code}: {body}"
        )

    try:
        payload = resp.json()
    except Exception as exc:
        raise EufyCloudError("Eufy domain lookup returned invalid JSON") from exc

    code = _native_error_code(payload)
    if code != 0:
        raise EufyCloudError(
            f"Eufy domain lookup failed ({code}): {_native_error_text(payload)}"
        )

    data = payload.get("data") if isinstance(payload, dict) else None
    domain = str(data.get("domain") if isinstance(data, dict) else "").strip()
    if not domain:
        raise EufyCloudError("Eufy domain lookup missing API domain")

    return f"https://{domain}"


def _native_session(
    profile: EufyCloudProfile,
    *,
    timeout: float,
    force_login: bool = False,
    captcha_id: str = "",
    captcha_code: str = "",
) -> tuple[str, str, bytes, dict[str, str]]:
    now = time.time()
    if not force_login:
        with _NATIVE_SESSION_LOCK:
            cached = _NATIVE_SESSIONS.get(profile.name)
            if isinstance(cached, dict):
                token = str(cached.get("token") or "").strip()
                api_base = str(cached.get("api_base") or "").strip()
                expires_at = float(cached.get("expires_at") or 0)
                session_key = cached.get("session_key")
                headers = cached.get("headers")
                if (
                    token
                    and api_base
                    and isinstance(session_key, bytes)
                    and isinstance(headers, dict)
                    and expires_at > now + _NATIVE_REFRESH_GRACE_SECONDS
                ):
                    return token, api_base, session_key, dict(headers)

    if not profile.native_email or not profile.native_password:
        raise EufyCloudError(
            f"Eufy profile '{profile.name}' missing cloud email/password"
        )

    country = str(profile.native_country or "US").strip().upper() or "US"
    api_base = _native_api_base(country, timeout=timeout, verify_tls=profile.verify_tls)
    req_headers = _native_headers(country)

    private_key = ec.generate_private_key(ec.SECP256R1())
    client_public_key = private_key.public_key().public_bytes(
        encoding=Encoding.X962,
        format=PublicFormat.UncompressedPoint,
    )
    server_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), bytes.fromhex(_EUFY_SERVER_PUBLIC_KEY)
    )
    shared_key = private_key.exchange(ec.ECDH(), server_public)

    login_payload = {
        "ab": country,
        "client_secret_info": {"public_key": client_public_key.hex()},
        "enc": 0,
        "email": str(profile.native_email),
        "password": _native_encrypt_password(str(profile.native_password), shared_key),
        "time_zone": _native_timezone_ms(),
        "transaction": str(int(time.time() * 1000)),
    }
    if captcha_id and captcha_code:
        login_payload["captcha_id"] = str(captcha_id)
        login_payload["answer"] = str(captcha_code)

    try:
        resp = requests.post(
            f"{api_base}/v2/passport/login_sec",
            json=login_payload,
            headers=req_headers,
            timeout=timeout,
            verify=profile.verify_tls,
        )
    except Exception as exc:
        raise EufyCloudError(f"Eufy cloud login request failed: {exc}") from exc

    if resp.status_code >= 400:
        body = (resp.text or "").strip().replace("\n", " ")[:120]
        raise EufyCloudError(
            f"Eufy cloud login returned HTTP {resp.status_code}: {body}"
        )

    try:
        payload = resp.json()
    except Exception as exc:
        raise EufyCloudError("Eufy cloud login returned invalid JSON") from exc

    code = _native_error_code(payload)
    if code != 0:
        msg = _native_error_text(payload)
        _native_raise_captcha_required(profile, payload, code, msg)
        raise EufyCloudError(f"Eufy cloud login failed ({code}): {msg}")

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise EufyCloudError("Eufy cloud login response missing data payload")

    token = str(data.get("auth_token") or "").strip()
    if not token:
        raise EufyCloudError("Eufy cloud login succeeded but auth token missing")

    # Eufy can rotate the response crypto key per login. Keep the fallback for
    # older responses that omit `server_secret_info`.
    response_public = str(
        (data.get("server_secret_info") or {}).get("public_key") or ""
    ).strip()
    if response_public:
        try:
            rotated_public = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), bytes.fromhex(response_public)
            )
            shared_key = private_key.exchange(ec.ECDH(), rotated_public)
        except Exception:
            pass

    try:
        expires_at = float(data.get("token_expires_at") or 0)
    except Exception:
        expires_at = 0
    if expires_at > 10_000_000_000:
        expires_at /= 1000.0
    if expires_at <= now:
        expires_at = now + 1800

    with _NATIVE_SESSION_LOCK:
        _NATIVE_SESSIONS[profile.name] = {
            "token": token,
            "api_base": api_base,
            "expires_at": expires_at,
            "session_key": shared_key,
            "headers": req_headers,
        }
    clear_native_captcha(profile.name)

    return token, api_base, shared_key, req_headers


def _native_request(
    profile: EufyCloudProfile,
    endpoint: str,
    *,
    payload: dict | None = None,
    timeout: float,
    retry: bool = True,
) -> dict:
    token, api_base, session_key, session_headers = _native_session(
        profile, timeout=timeout
    )
    url = f"{api_base.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = dict(session_headers)
    headers["x-auth-token"] = token
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=payload or {},
            timeout=timeout,
            verify=profile.verify_tls,
        )
    except Exception as exc:
        raise EufyCloudError(
            f"Eufy cloud request failed for {endpoint}: {exc}"
        ) from exc

    if resp.status_code == 401 and retry:
        _clear_native_session(profile.name)
        return _native_request(
            profile,
            endpoint,
            payload=payload,
            timeout=timeout,
            retry=False,
        )

    if resp.status_code >= 400:
        raise EufyCloudError(
            f"Eufy cloud endpoint {endpoint} returned HTTP {resp.status_code}"
        )

    try:
        body = resp.json()
    except Exception as exc:
        raise EufyCloudError(
            f"Eufy cloud endpoint {endpoint} returned invalid JSON"
        ) from exc

    code = _native_error_code(body)
    if code != 0:
        msg = _native_error_text(body)
        authish = (
            "token" in msg.lower()
            or "auth" in msg.lower()
            or code
            in {
                26051,
                26052,
                26053,
            }
        )
        if retry and authish:
            _clear_native_session(profile.name)
            return _native_request(
                profile,
                endpoint,
                payload=payload,
                timeout=timeout,
                retry=False,
            )
        raise EufyCloudError(f"Eufy cloud error on {endpoint} ({code}): {msg}")

    if not isinstance(body, dict):
        return {}

    encrypted_data = body.get("data")
    if isinstance(encrypted_data, str) and encrypted_data.strip():
        decrypted = _native_decrypt_payload(encrypted_data, session_key)
        merged = dict(body)
        merged["data"] = decrypted
        return merged

    return body


def _native_snapshot_url(device: dict) -> str:
    image_urls, _ = _native_media_candidates(device, api_base=None)
    return image_urls[0] if image_urls else ""


def _native_normalize_media_url(raw: str, api_base: str | None) -> str:
    text = str(raw or "").strip().replace("\\/", "/")
    if not text:
        return ""
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith("/"):
        if not api_base:
            return ""
        return f"{api_base.rstrip('/')}{text}"
    parsed = urlparse(text)
    if parsed.scheme.lower() in {"http", "https", "rtsp", "rtsps"}:
        return text
    return ""


def _native_candidate_score(path: str, value: str) -> int:
    p = str(path or "").lower()
    v = str(value or "").lower()
    score = 0
    if any(tok in p for tok in ("cover", "snapshot", "picture", "thumb", "image")):
        score += 80
    if any(tok in p for tok in ("stream", "live", "rtsp", "hls")):
        score += 35
    if any(tok in v for tok in ("snapshot", "cover", "thumb", "image")):
        score += 30
    if any(tok in v for tok in ("rtsp://", ".m3u8", "/live", "stream")):
        score += 15
    if any(tok in v for tok in (".jpg", ".jpeg", ".png", ".webp")):
        score += 25
    return score


def _native_walk_string_values(data: object, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(data, str):
        out.append((path, data))
    elif isinstance(data, dict):
        for key, value in data.items():
            key_path = f"{path}.{key}" if path else str(key)
            out.extend(_native_walk_string_values(value, key_path))
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            idx_path = f"{path}[{idx}]"
            out.extend(_native_walk_string_values(value, idx_path))
    return out


def _native_media_candidates(
    device: dict, *, api_base: str | None
) -> tuple[list[str], list[str]]:
    if not isinstance(device, dict):
        return [], []

    explicit_keys = (
        "cover_path",
        "picture_url",
        "snapshot_url",
        "image_url",
        "thumb_url",
        "thumbnail_url",
        "preview_url",
        "url",
        "stream_url",
        "hls_url",
        "rtsp_url",
    )
    candidates: list[tuple[int, str, str]] = []

    for key in explicit_keys:
        value = device.get(key)
        if isinstance(value, str):
            normalized = _native_normalize_media_url(value, api_base)
            if normalized:
                candidates.append(
                    (100 + _native_candidate_score(key, normalized), key, normalized)
                )

    # Some Eufy payloads hide usable URLs in nested `params` or metadata
    # dictionaries. Walk all string fields and score likely media links.
    for path, value in _native_walk_string_values(device):
        normalized = _native_normalize_media_url(value, api_base)
        if not normalized:
            continue
        score = _native_candidate_score(path, normalized)
        if score <= 0:
            continue
        candidates.append((score, path, normalized))

    if not candidates:
        return [], []

    candidates.sort(key=lambda item: item[0], reverse=True)

    seen: set[str] = set()
    image_urls: list[str] = []
    stream_urls: list[str] = []

    for _score, _path, value in candidates:
        if value in seen:
            continue
        seen.add(value)
        lower = value.lower()
        is_stream = lower.startswith(("rtsp://", "rtsps://")) or ".m3u8" in lower
        if is_stream:
            stream_urls.append(value)
        else:
            image_urls.append(value)

    return image_urls, stream_urls


def _native_fetch_stream_frame(stream_url: str, *, timeout: float) -> tuple[bytes, str]:
    stream_url = str(stream_url or "").strip()
    if not stream_url:
        raise EufyCloudError("Missing stream URL")

    with tempfile.NamedTemporaryFile(
        prefix="eufy_frame_", suffix=".jpg", delete=False
    ) as tmp:
        output_path = tmp.name

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]
    lower = stream_url.lower()
    if lower.startswith(("rtsp://", "rtsps://")):
        # WAN/cloud RTSP endpoints can stall on socket reads; rw_timeout keeps
        # this fallback from hanging screenshot workers.
        cmd.extend(
            [
                "-rtsp_transport",
                "tcp",
                "-rw_timeout",
                str(int(max(timeout, 1.0) * 1_000_000)),
            ]
        )
    cmd.extend(["-i", stream_url, "-frames:v", "1", "-q:v", "2", output_path])

    run_timeout = max(5.0, min(float(timeout or 20.0), 30.0))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=run_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EufyCloudError(
            f"ffmpeg stream snapshot timed out after {run_timeout:.1f}s"
        ) from exc
    except FileNotFoundError as exc:
        raise EufyCloudError("ffmpeg is not installed") from exc
    finally:
        # Keep cleanup centralized below to avoid unlink races.
        pass

    try:
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise EufyCloudError(f"ffmpeg stream snapshot failed: {err[:240]}")
        if not os.path.exists(output_path):
            raise EufyCloudError("ffmpeg did not produce a frame")
        payload = open(output_path, "rb").read()
        if len(payload) < 128:
            raise EufyCloudError("ffmpeg produced an invalid frame")
        return payload, "image/jpeg"
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass


def _native_online(device: dict) -> bool:
    val = device.get("is_online", device.get("online", device.get("status")))
    if val is None or val == "":
        return True
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    text = str(val).strip().lower()
    return text not in {"0", "false", "offline", "off", "disconnected"}


def _native_list_devices(profile: EufyCloudProfile, *, timeout: float) -> list[dict]:
    payload = _native_request(profile, "v2/app/get_devs_list", timeout=timeout)
    raw_devices = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_devices, list):
        raise EufyCloudError("Eufy cloud devices payload is missing data list")

    out: list[dict] = []
    for item in raw_devices:
        if not isinstance(item, dict):
            continue
        did = str(
            item.get("device_sn")
            or item.get("device_id")
            or item.get("id")
            or item.get("serialNumber")
            or ""
        ).strip()
        if not did:
            continue

        name = str(
            item.get("device_name")
            or item.get("name")
            or item.get("label")
            or item.get("nickname")
            or did
        ).strip()
        image_urls, stream_urls = _native_media_candidates(item, api_base=None)
        out.append(
            {
                "device_id": did,
                "name": name,
                "online": _native_online(item),
                "snapshot": bool(image_urls or stream_urls),
                "model": str(
                    item.get("device_model") or item.get("model") or ""
                ).strip(),
                "station": str(
                    item.get("station_sn") or item.get("station") or ""
                ).strip(),
            }
        )

    out.sort(key=lambda d: str(d.get("name") or "").lower())
    return out


def _native_fetch_image(
    profile: EufyCloudProfile,
    image_url: str,
    *,
    timeout: float,
) -> tuple[bytes, str]:
    image_url = str(image_url or "").strip()
    if not image_url:
        raise EufyCloudError("Eufy cloud device has no cover image URL")

    token, _api_base, _session_key, session_headers = _native_session(
        profile, timeout=timeout
    )
    last_error = ""
    for headers in (
        {**session_headers, "x-auth-token": token},
        {"Authorization": f"Bearer {token}"},
        {},
    ):
        try:
            resp = requests.get(
                image_url,
                headers=headers,
                timeout=timeout,
                verify=profile.verify_tls,
            )
        except Exception as exc:
            last_error = str(exc)
            continue

        if resp.status_code >= 400:
            last_error = f"HTTP {resp.status_code}"
            continue

        content_type = (
            str(resp.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        )
        if content_type.startswith("image/"):
            return resp.content, content_type or "image/jpeg"

        try:
            payload = resp.json()
        except Exception:
            last_error = f"non-image content-type {content_type or 'unknown'}"
            continue

        if isinstance(payload, dict):
            b64 = str(
                payload.get("image_base64")
                or payload.get("snapshot_base64")
                or payload.get("jpeg_base64")
                or ""
            ).strip()
            if b64:
                try:
                    return base64.b64decode(b64), "image/jpeg"
                except Exception:
                    last_error = "invalid base64 image payload"
                    continue
            redirect = str(
                payload.get("snapshot_url")
                or payload.get("image_url")
                or payload.get("url")
                or ""
            ).strip()
            if redirect:
                return _native_fetch_image(profile, redirect, timeout=timeout)

        last_error = f"unsupported payload ({content_type or 'unknown'})"

    raise EufyCloudError(
        f"Failed fetching Eufy snapshot image for URL {image_url}: {last_error}"
    )


def _native_fetch_snapshot(
    profile: EufyCloudProfile,
    device_id: str,
    *,
    timeout: float,
) -> tuple[bytes, str]:
    _token, api_base, _session_key, _session_headers = _native_session(
        profile, timeout=timeout
    )
    payload = _native_request(profile, "v2/app/get_devs_list", timeout=timeout)
    raw_devices = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_devices, list):
        raise EufyCloudError("Eufy cloud devices payload is missing data list")

    did = str(device_id or "").strip()
    if not did:
        raise EufyCloudError("Missing Eufy device id")

    target = next(
        (
            d
            for d in raw_devices
            if isinstance(d, dict)
            and str(
                d.get("device_sn")
                or d.get("device_id")
                or d.get("id")
                or d.get("serialNumber")
                or ""
            ).strip()
            == did
        ),
        None,
    )
    if not isinstance(target, dict):
        raise EufyCloudError(f"Eufy cloud device '{did}' not found")

    image_urls, stream_urls = _native_media_candidates(target, api_base=api_base)
    attempts: list[str] = []

    for image_url in image_urls:
        try:
            return _native_fetch_image(profile, image_url, timeout=timeout)
        except EufyCloudError as exc:
            attempts.append(f"image:{exc}")
            continue

    for stream_url in stream_urls:
        try:
            return _native_fetch_stream_frame(stream_url, timeout=timeout)
        except EufyCloudError as exc:
            attempts.append(f"stream:{exc}")
            continue

    detail = f" (attempts: {' | '.join(attempts[:3])})" if attempts else ""
    raise EufyCloudError(
        f"Eufy cloud device '{did}' has no usable snapshot or stream URL in API response{detail}"
    )


def _webportal_lock(profile_name: str) -> threading.Lock:
    key = str(profile_name or "default").strip().lower() or "default"
    with _NATIVE_SESSION_LOCK:
        lock = _WEBPORTAL_CAPTURE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _WEBPORTAL_CAPTURE_LOCKS[key] = lock
        return lock


def clear_webportal_pin_backoff(profile: str = "default") -> None:
    """Clear PIN backoff state for a profile."""

    key = str(profile or "default").strip().lower() or "default"
    with _NATIVE_SESSION_LOCK:
        _WEBPORTAL_PIN_BACKOFF_UNTIL.pop(key, None)


def get_webportal_pin_backoff_remaining(profile: str = "default") -> int:
    """Return remaining PIN backoff seconds for a profile (0 means clear)."""

    return _webportal_pin_backoff_remaining(profile)


def _webportal_set_pin_backoff(profile: str) -> int:
    key = str(profile or "default").strip().lower() or "default"
    until = time.time() + _WEBPORTAL_PIN_BACKOFF_SECONDS
    with _NATIVE_SESSION_LOCK:
        _WEBPORTAL_PIN_BACKOFF_UNTIL[key] = until
    return _WEBPORTAL_PIN_BACKOFF_SECONDS


def _webportal_pin_backoff_remaining(profile: str) -> int:
    key = str(profile or "default").strip().lower() or "default"
    with _NATIVE_SESSION_LOCK:
        until = float(_WEBPORTAL_PIN_BACKOFF_UNTIL.get(key) or 0.0)
    remaining = int(until - time.time())
    if remaining <= 0:
        with _NATIVE_SESSION_LOCK:
            _WEBPORTAL_PIN_BACKOFF_UNTIL.pop(key, None)
        return 0
    return remaining


def _webportal_url(profile: EufyCloudProfile) -> str:
    raw = str(
        profile.webportal_url or "https://mysecurity.eufylife.com/#/camera"
    ).strip()
    if not raw:
        raw = "https://mysecurity.eufylife.com/#/camera"
    if "#/" not in raw:
        raw = raw.rstrip("/") + "/#/camera"
    return raw


def _webportal_user_data_dir(profile: EufyCloudProfile) -> str:
    custom = str(profile.webportal_user_data_dir or "").strip()
    if custom:
        return custom
    base_dir = Path(str(config.DATABASE_PATH)).resolve().parent
    target = base_dir / "eufy_webportal" / profile.name
    return str(target)


def _webportal_device_label(profile_name: str, device_id: str) -> str:
    try:
        from app.utils import template_manager

        prefix = (
            f"eufy://{str(profile_name or 'default').strip().lower() or 'default'}/"
        )
        did = str(device_id or "").strip()
        if not did:
            return ""
        target = prefix + did
        for template_name, tmpl in template_manager.get_templates().items():
            url = str((tmpl or {}).get("url") or "").strip()
            if url == target:
                return str(template_name or "").strip()
    except Exception:
        return ""
    return ""


def _webportal_find_visible(driver, xpaths: list[str]):
    # Keep selectors explicit and deterministic to avoid brittle retries.
    for xp in xpaths:
        try:
            nodes = driver.find_elements("xpath", xp)
        except Exception:
            continue
        for node in nodes:
            try:
                if node.is_displayed():
                    return node
            except Exception:
                continue
    return None


def _webportal_click(driver, element) -> None:
    try:
        element.click()
        return
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
    except Exception:
        return


def _webportal_wait_for_render(driver, *, timeout: float) -> None:
    """Wait until login/pin/camera UI is visible before interacting."""

    deadline = time.time() + max(2.0, float(timeout or 0.0))
    while time.time() < deadline:
        if _webportal_find_visible(
            driver,
            [
                "//input[@type='email']",
                "//input[@type='password']",
                "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha')]",
                "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verification code')]",
                "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'safety pin')]",
                "//video",
                "//canvas",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'live view')]",
                "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'all devices')]",
            ],
        ):
            return
        time.sleep(0.2)


def _webportal_login_button(driver):
    return _webportal_find_visible(
        driver,
        [
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
            "//button[@type='submit']",
        ],
    )


def _webportal_captcha_input(driver):
    return _webportal_find_visible(
        driver,
        [
            "//input[@name='craphics']",
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verification code')]",
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm you are not a robot')]",
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha')]",
        ],
    )


def _webportal_captcha_image(driver, captcha_input):
    # Prefer direct captcha media near the input, with a deterministic fallback
    # to any visible captcha-like image/canvas on the page.
    candidates = [
        "//input[@name='craphics']/following::div[contains(@class,'craphics-box')]//img[1]",
        "//input[@name='craphics']/following::img[1]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verification code')]/following::div[contains(@class,'craphics-box')]//img[1]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verification code')]/following::img[1]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm you are not a robot')]/following::img[1]",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm you are not a robot')]/following::canvas[1]",
        "//img[contains(translate(@src,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha')]",
        "//img[contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha')]",
        "//img[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'craphics')]",
        "//canvas[contains(@class,'captcha')]",
    ]
    node = _webportal_find_visible(driver, candidates)
    if node is not None:
        return node

    # Last resort: use the nearest visible image/canvas by Manhattan distance.
    try:
        cx = int((captcha_input.rect or {}).get("x", 0))
        cy = int((captcha_input.rect or {}).get("y", 0))
    except Exception:
        return None
    nearest = None
    nearest_dist = 10**9
    try:
        media_nodes = driver.find_elements("css selector", "img, canvas")
    except Exception:
        media_nodes = []
    for node in media_nodes:
        try:
            if not node.is_displayed():
                continue
            rect = node.rect or {}
            nx = int(rect.get("x", 0))
            ny = int(rect.get("y", 0))
            w = int(rect.get("width", 0))
            h = int(rect.get("height", 0))
            if w < 40 or h < 20:
                continue
            dist = abs(nx - cx) + abs(ny - cy)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = node
        except Exception:
            continue
    return nearest


def _webportal_ocr_captcha_codes(driver, captcha_input, *, timeout: float) -> list[str]:
    def _crop_from_full_screenshot(
        full_png: bytes,
        *,
        rect: dict[str, object] | None,
        pad_x: int = 8,
        pad_y: int = 6,
    ) -> bytes:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(full_png)) as full:
                full = full.convert("RGB")
                width, height = full.size
                if width < 8 or height < 8:
                    return b""
                if not rect:
                    return b""
                rx = int(float(rect.get("x", 0) or 0))
                ry = int(float(rect.get("y", 0) or 0))
                rw = int(float(rect.get("width", 0) or 0))
                rh = int(float(rect.get("height", 0) or 0))
                if rw < 20 or rh < 12:
                    return b""
                left = max(0, rx - pad_x)
                top = max(0, ry - pad_y)
                right = min(width, rx + rw + pad_x)
                bottom = min(height, ry + rh + pad_y)
                if right - left < 20 or bottom - top < 12:
                    return b""
                crop = full.crop((left, top, right, bottom))
                with io.BytesIO() as out:
                    crop.save(out, format="PNG")
                    return out.getvalue()
        except Exception:
            return b""

    def _candidate_images(captcha_image) -> list[bytes]:
        out: list[bytes] = []
        try:
            element_png = captcha_image.screenshot_as_png if captcha_image else b""
        except Exception:
            element_png = b""
        if element_png:
            out.append(element_png)

        # Some Eufy variants render captcha via canvas/layering and element-level
        # screenshots are blank/noisy. Add full-page crops around likely regions.
        try:
            full_png = driver.get_screenshot_as_png()
        except Exception:
            full_png = b""
        if not full_png:
            return out

        try:
            input_rect = captcha_input.rect or {}
        except Exception:
            input_rect = {}
        try:
            image_rect = (captcha_image.rect or {}) if captcha_image is not None else {}
        except Exception:
            image_rect = {}

        # 1) Exact captcha media rect when available.
        cropped = _crop_from_full_screenshot(full_png, rect=image_rect)
        if cropped:
            out.append(cropped)

        # 2) Right side of captcha input (where many Eufy pages place captcha).
        try:
            ix = int(float(input_rect.get("x", 0) or 0))
            iy = int(float(input_rect.get("y", 0) or 0))
            iw = int(float(input_rect.get("width", 0) or 0))
            ih = int(float(input_rect.get("height", 0) or 0))
        except Exception:
            ix = iy = iw = ih = 0
        if iw > 0 and ih > 0:
            candidate_rect = {
                "x": max(0, ix + iw - int(max(ih * 2.8, 120))),
                "y": max(0, iy - int(max(ih * 0.35, 6))),
                "width": int(max(ih * 2.8, 120)),
                "height": int(max(ih * 1.7, 36)),
            }
            cropped = _crop_from_full_screenshot(full_png, rect=candidate_rect)
            if cropped:
                out.append(cropped)
        return out

    for attempt in range(4):
        captcha_image = _webportal_captcha_image(driver, captcha_input)
        images = _candidate_images(captcha_image)
        for image_bytes in images:
            if not image_bytes:
                continue
            codes = _native_ollama_codes(
                image_bytes, timeout=max(2.0, min(timeout, 8.0))
            )
            if codes:
                return codes
        if attempt < 3:
            _webportal_refresh_captcha(driver, captcha_input)
            time.sleep(0.25)
    return []


def _webportal_refresh_captcha(driver, captcha_input) -> None:
    button = _webportal_find_visible(
        driver,
        [
            "//div[contains(@class,'craphics-box')]//i[contains(@class,'craphics-box-icon')]",
            "//input[@name='craphics']/following::i[contains(@class,'craphics-box-icon')][1]",
        ],
    )
    if button is not None:
        _webportal_click(driver, button)
        time.sleep(0.3)


def _webportal_pin_invalid_message(driver):
    return _webportal_find_visible(
        driver,
        [
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invalid') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pin')]",
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'incorrect') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pin')]",
        ],
    )


def _webportal_country_name(native_country: str) -> str:
    raw = str(native_country or "").strip()
    if not raw:
        return "United States"
    key = raw.upper()
    aliases = {
        "US": "United States",
        "USA": "United States",
        "CA": "Canada",
        "UK": "United Kingdom",
        "GB": "United Kingdom",
        "AU": "Australia",
        "DE": "Germany",
        "FR": "France",
        "ES": "Spain",
        "IT": "Italy",
        "MX": "Mexico",
        "BR": "Brazil",
        "JP": "Japan",
        "KR": "South Korea",
        "SG": "Singapore",
    }
    return aliases.get(key, raw)


def _webportal_select_region_if_needed(
    driver,
    profile: EufyCloudProfile,
    *,
    timeout: float,
) -> None:
    target_country = _webportal_country_name(profile.native_country)
    target_lower = target_country.lower()
    region_combobox = _webportal_find_visible(
        driver,
        [
            "//form[contains(@class,'login-form')]//div[contains(@class,'ant-select-selection') and @role='combobox']",
            "//div[contains(@class,'ant-select-selection') and @role='combobox']",
        ],
    )
    if region_combobox is None:
        return

    region_text = str(region_combobox.text or "").strip().lower()
    if (
        region_text
        and "select your region" not in region_text
        and target_lower in region_text
    ):
        return

    _webportal_click(driver, region_combobox)
    deadline = time.time() + max(2.0, min(float(timeout), 10.0))
    option = None
    while time.time() < deadline:
        option = _webportal_find_visible(
            driver,
            [
                f"//li[contains(@class,'ant-select-dropdown-menu-item') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{target_lower}')]",
            ],
        )
        if option is not None:
            break
        time.sleep(0.2)

    if option is None:
        raise EufyCloudError(
            f"Eufy web portal region selector could not find '{target_country}'."
        )

    _webportal_click(driver, option)
    time.sleep(0.5)
    ok_button = _webportal_find_visible(
        driver,
        [
            "//div[contains(@class,'ant-modal')]//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
        ],
    )
    if ok_button is not None:
        _webportal_click(driver, ok_button)
        time.sleep(0.4)


def _webportal_login_if_needed(
    driver,
    profile: EufyCloudProfile,
    *,
    timeout: float,
) -> None:
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, max(3.0, min(float(timeout), 20.0)))
    try:
        wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass
    _webportal_wait_for_render(driver, timeout=timeout)
    _webportal_select_region_if_needed(driver, profile, timeout=timeout)

    email_selectors = [
        "//input[@type='email']",
        "//input[@name='email']",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]",
    ]
    password_selectors = [
        "//input[@type='password']",
        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'password')]",
    ]
    email = _webportal_find_visible(driver, email_selectors)
    password = _webportal_find_visible(driver, password_selectors)
    captcha_input = _webportal_captcha_input(driver)
    # If the login form is not visible, we are likely already authenticated.
    if not (email or password or captcha_input):
        return

    # Some Eufy variants hide/lock the email field once remembered, so only
    # treat password as mandatory for an interactive login attempt.
    if not password:
        return

    def _login_form_still_visible() -> bool:
        return bool(
            _webportal_find_visible(driver, email_selectors)
            or _webportal_find_visible(driver, password_selectors)
            or _webportal_captcha_input(driver)
        )

    if not profile.native_email or not profile.native_password:
        raise EufyCloudError(
            "Eufy web portal login is required; save native email/password in the selected profile."
        )

    max_attempts = 5
    saw_captcha = False
    for attempt in range(max_attempts):
        email = _webportal_find_visible(driver, email_selectors)
        password = _webportal_find_visible(driver, password_selectors)
        if password is None:
            return

        if email is not None:
            try:
                email.clear()
            except Exception:
                pass
            email.send_keys(profile.native_email)
        try:
            password.clear()
        except Exception:
            pass
        password.send_keys(profile.native_password)

        captcha_input = _webportal_captcha_input(driver)
        code_candidates = [""]
        if captcha_input is not None:
            saw_captcha = True
            codes = _webportal_ocr_captcha_codes(
                driver, captcha_input, timeout=max(2.0, timeout / 2.0)
            )
            if not codes:
                raise EufyCloudError(
                    "Eufy web portal captcha is present but OCR could not extract a code."
                )
            code_candidates = codes[:6]

        for code in code_candidates:
            captcha_input = _webportal_captcha_input(driver)
            if captcha_input is not None and code:
                try:
                    captcha_input.clear()
                except Exception:
                    pass
                captcha_input.send_keys(code)

            login_btn = _webportal_login_button(driver)
            if login_btn is not None:
                _webportal_click(driver, login_btn)
            else:
                try:
                    password.send_keys(Keys.ENTER)
                except Exception:
                    pass

            deadline = time.time() + 3.0
            while time.time() < deadline:
                if not _login_form_still_visible():
                    return
                time.sleep(0.2)

        captcha_input = _webportal_captcha_input(driver)
        if captcha_input is not None:
            _webportal_refresh_captcha(driver, captcha_input)

    if saw_captcha:
        raise EufyCloudError(
            "Eufy web portal login captcha could not be solved automatically after multiple attempts."
        )
    raise EufyCloudError(
        "Eufy web portal login did not complete after multiple attempts."
    )


def _webportal_verify_pin_if_needed(
    driver,
    profile: EufyCloudProfile,
    *,
    timeout: float,
) -> None:
    from selenium.webdriver.support.ui import WebDriverWait

    pin_input = _webportal_find_visible(
        driver,
        [
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'safety pin')]",
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pin')]",
        ],
    )
    if not pin_input:
        clear_webportal_pin_backoff(profile.name)
        return

    if not profile.webportal_pin:
        backoff_seconds = _webportal_set_pin_backoff(profile.name)
        raise EufyCloudError(
            f"Web portal Safety PIN prompt detected. Save `webportal_pin` in profile and retry (backing off {backoff_seconds}s)."
        )

    try:
        pin_input.clear()
    except Exception:
        pass
    pin_input.send_keys(profile.webportal_pin)

    confirm = _webportal_find_visible(
        driver,
        [
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm')]",
            "//button[@type='submit']",
        ],
    )
    if confirm:
        _webportal_click(driver, confirm)

    wait = WebDriverWait(driver, max(3.0, min(float(timeout), 15.0)))
    try:
        wait.until(
            lambda d: (
                _webportal_find_visible(
                    d,
                    [
                        "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'safety pin')]",
                    ],
                )
                is None
            )
        )
    except Exception:
        pass

    if _webportal_find_visible(
        driver,
        [
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'safety pin')]",
        ],
    ):
        backoff_seconds = _webportal_set_pin_backoff(profile.name)
        suffix = ""
        if _webportal_pin_invalid_message(driver) is not None:
            suffix = " (portal rejected Safety PIN)"
        raise EufyCloudError(
            f"Eufy web portal Safety PIN verification did not complete{suffix}; backing off {backoff_seconds}s before retry."
        )

    clear_webportal_pin_backoff(profile.name)


def _webportal_select_camera(
    driver,
    profile: EufyCloudProfile,
    device_id: str,
) -> None:
    label = _webportal_device_label(profile.name, device_id)
    candidates = []
    if label:
        safe = label.replace("'", "")
        if safe:
            candidates.extend(
                [
                    f"//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{safe.lower()}')]",
                ]
            )
    did = str(device_id or "").strip()
    if did:
        candidates.append(f"//*[contains(., '{did}')]")

    for xp in candidates:
        node = _webportal_find_visible(driver, [xp])
        if not node:
            continue
        _webportal_click(driver, node)
        time.sleep(0.5)
        break


def _webportal_capture_frame(driver) -> tuple[bytes, str]:
    # Prefer media surfaces when available. Fall back to the full page so we
    # still return a useful frame during portal layout changes.
    media_nodes = []
    try:
        media_nodes = driver.find_elements("css selector", "video, canvas")
    except Exception:
        media_nodes = []

    best = None
    best_area = 0
    for node in media_nodes:
        try:
            if not node.is_displayed():
                continue
            size = node.size or {}
            area = int(size.get("width", 0)) * int(size.get("height", 0))
            if area > best_area:
                best = node
                best_area = area
        except Exception:
            continue

    if best is not None and best_area >= 12_000:
        try:
            payload = best.screenshot_as_png
            if payload and len(payload) > 128:
                return payload, "image/png"
        except Exception:
            pass

    payload = driver.get_screenshot_as_png()
    if not payload or len(payload) < 128:
        raise EufyCloudError("Web portal screenshot capture produced an invalid frame")
    return payload, "image/png"


def _webportal_assert_capture_ready(driver) -> None:
    current_url = str(getattr(driver, "current_url", "") or "").lower()
    if "/#/login" in current_url:
        raise EufyCloudError(
            "Eufy web portal session is not signed in for this profile. Open web portal once and complete login/captcha."
        )

    login_inputs_visible = _webportal_find_visible(
        driver,
        [
            "//input[@type='email']",
            "//input[@type='password']",
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm you are not a robot')]",
        ],
    )
    if login_inputs_visible:
        raise EufyCloudError(
            "Eufy web portal still shows login/captcha fields. Complete login and retry capture."
        )

    pin_prompt_visible = _webportal_find_visible(
        driver,
        [
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'safety pin')]",
            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please enter safety pin')]",
        ],
    )
    if pin_prompt_visible:
        raise EufyCloudError(
            "Eufy web portal requires Safety PIN verification for capture."
        )

    marketing_splash = _webportal_find_visible(
        driver,
        [
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edge ecosystem makes life better')]",
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'visit eufy.com to learn more')]",
        ],
    )
    if marketing_splash:
        raise EufyCloudError(
            "Eufy web portal is still on the public marketing/login splash. Complete login and camera selection first."
        )


def _webportal_fetch_snapshot(
    profile: EufyCloudProfile,
    device_id: str,
    *,
    timeout: float,
) -> tuple[bytes, str]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    portal_url = _webportal_url(profile)
    base_user_data_dir = _webportal_user_data_dir(profile)
    os.makedirs(base_user_data_dir, exist_ok=True)

    def _build_options(user_data_dir: str, *, use_profile_dir: bool) -> Options:
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,900")
        # Reduce obvious webdriver fingerprints; Eufy often presents captcha
        # challenges more aggressively when automation is trivially detectable.
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument(f"--user-data-dir={user_data_dir}")
        # Use one profile per integration profile to keep login cookies isolated.
        # When we fall back to an ephemeral user-data-dir, skip profile-directory
        # to avoid lock/collision errors.
        if use_profile_dir:
            opts.add_argument(f"--profile-directory=glimpser-eufy-{profile.name}")
        return opts

    lock = _webportal_lock(profile.name)
    with lock:
        remaining = _webportal_pin_backoff_remaining(profile.name)
        if remaining > 0:
            raise EufyCloudError(
                f"Eufy web portal PIN is in backoff for profile '{profile.name}' ({remaining}s remaining)."
            )
        driver = None
        temp_user_data_dir = ""
        try:
            opts = _build_options(base_user_data_dir, use_profile_dir=True)
            service = Service()
            driver = webdriver.Chrome(service=service, options=opts)
        except Exception as first_exc:
            try:
                from webdriver_manager.chrome import ChromeDriverManager

                opts = _build_options(base_user_data_dir, use_profile_dir=True)
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=opts)
            except Exception as second_exc:
                # If the persistent profile is locked by an interactive session,
                # fall back to an isolated temporary profile for this capture.
                try:
                    temp_user_data_dir = tempfile.mkdtemp(
                        prefix=f"glimpser_eufy_{profile.name}_"
                    )
                    opts = _build_options(temp_user_data_dir, use_profile_dir=False)
                    service = Service()
                    driver = webdriver.Chrome(service=service, options=opts)
                except Exception as third_exc:
                    raise EufyCloudError(
                        f"Unable to start Chrome for Eufy web portal mode: {first_exc} | {second_exc} | {third_exc}"
                    ) from third_exc

        try:
            # Best-effort stealth tweaks for websites that branch on webdriver.
            try:
                driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": (
                            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                        )
                    },
                )
            except Exception:
                pass

            page_timeout = max(8.0, min(float(timeout or 20.0), 45.0))
            driver.set_page_load_timeout(page_timeout)
            driver.get(portal_url)
            _webportal_login_if_needed(driver, profile, timeout=page_timeout)
            _webportal_verify_pin_if_needed(driver, profile, timeout=page_timeout)
            _webportal_select_camera(driver, profile, device_id)
            # Some Eufy flows show the Safety PIN prompt only after opening a
            # camera tile. Re-check here so capture can proceed without a
            # separate manual bootstrap round-trip.
            for _ in range(6):
                _webportal_verify_pin_if_needed(driver, profile, timeout=page_timeout)
                if (
                    _webportal_find_visible(
                        driver,
                        [
                            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'safety pin')]",
                            "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please enter safety pin')]",
                        ],
                    )
                    is None
                ):
                    break
                time.sleep(0.5)
            time.sleep(1.0)
            _webportal_assert_capture_ready(driver)
            payload, content_type = _webportal_capture_frame(driver)
            clear_webportal_pin_backoff(profile.name)
            return payload, content_type
        finally:
            try:
                driver.quit()
            except Exception:
                pass
            if temp_user_data_dir:
                try:
                    shutil.rmtree(temp_user_data_dir, ignore_errors=True)
                except Exception:
                    pass


def submit_native_captcha(
    profile: str,
    captcha_code: str,
    *,
    timeout: float = 20.0,
) -> None:
    """Submit a pending Eufy cloud API captcha answer."""

    key = str(profile or "default").strip().lower() or "default"
    prof = resolve_profile(key)
    if not prof:
        raise EufyCloudError(f"Eufy cloud profile '{key}' is not configured")
    if prof.mode not in {"native", "webportal"}:
        raise EufyCloudError(f"Eufy profile '{key}' is not in web portal/cloud mode")

    challenge = get_native_captcha(key)
    if not challenge:
        raise EufyCloudError(f"No pending captcha challenge for profile '{key}'")

    answer = str(captcha_code or "").strip()
    if not answer:
        raise EufyCloudError("Captcha answer is required")

    _clear_native_session(key)
    _native_session(
        prof,
        timeout=timeout,
        force_login=True,
        captcha_id=str(challenge.get("captcha_id") or ""),
        captcha_code=answer,
    )


def list_devices(profile: str = "default", *, timeout: float = 12.0) -> list[dict]:
    """List devices for a configured Eufy profile."""

    prof = resolve_profile(profile)
    if not prof:
        raise EufyCloudError(f"Eufy cloud profile '{profile}' is not configured")

    if _EUFY_EMULATOR_ONLY and prof.mode != "emulator":
        raise EufyCloudError(
            "Eufy web/native cloud modes are disabled. Use VM / Emulator (ADB)."
        )

    if prof.mode == "emulator":
        return _emulator_device_entries(prof)

    if prof.mode in {"native", "webportal"}:
        try:
            return _native_list_devices(prof, timeout=timeout)
        except EufyCaptchaRequired:
            solved = solve_cloud_captcha(
                profile,
                timeout=min(timeout, 10.0),
                max_rounds=3,
            )
            if solved.get("solved"):
                return _native_list_devices(prof, timeout=timeout)
            raise

    ensure_bridge_running(profile)

    url = _join_url(prof.bridge_url, prof.devices_path)
    try:
        resp = requests.get(
            url,
            headers=_headers(prof),
            timeout=timeout,
            verify=prof.verify_tls,
        )
    except Exception as exc:
        raise EufyCloudError(f"Bridge request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise EufyCloudError(
            f"Bridge returned HTTP {resp.status_code} for {prof.devices_path}"
        )

    try:
        payload = resp.json()
    except Exception as exc:
        raise EufyCloudError("Bridge devices response is not valid JSON") from exc

    out: list[dict] = []
    for item in _extract_devices(payload):
        did = str(
            item.get("device_id")
            or item.get("id")
            or item.get("serialNumber")
            or item.get("serial")
            or ""
        ).strip()
        if not did:
            continue
        name = str(
            item.get("name") or item.get("label") or item.get("nickname") or did
        ).strip()
        out.append(
            {
                "device_id": did,
                "name": name,
                "online": bool(item.get("online", True)),
                "snapshot": bool(
                    item.get("snapshot", True) or item.get("supports_snapshot", True)
                ),
                "model": str(item.get("model") or "").strip(),
                "station": str(
                    item.get("station") or item.get("homebase") or ""
                ).strip(),
            }
        )

    out.sort(key=lambda d: str(d.get("name") or "").lower())
    return out


def _snapshot_url_for_device(profile: EufyCloudProfile, device_id: str) -> str:
    device_id = str(device_id or "").strip()
    if not device_id:
        raise EufyCloudError("Missing Eufy device id")

    path = profile.snapshot_path
    if "{device_id}" in path:
        path = path.replace("{device_id}", quote(device_id, safe=""))
    elif path.endswith("/"):
        path = path + quote(device_id, safe="")
    else:
        sep = "&" if "?" in path else "?"
        path = f"{path}{sep}device_id={quote(device_id, safe='')}"
    return _join_url(profile.bridge_url, path)


def fetch_snapshot(
    profile: str,
    device_id: str,
    *,
    timeout: float = 20.0,
) -> tuple[bytes, str]:
    """Fetch a snapshot for ``device_id`` from the configured profile."""

    prof = resolve_profile(profile)
    if not prof:
        raise EufyCloudError(f"Eufy cloud profile '{profile}' is not configured")

    if _EUFY_EMULATOR_ONLY and prof.mode != "emulator":
        raise EufyCloudError(
            "Eufy web/native cloud modes are disabled. Use VM / Emulator (ADB)."
        )

    if prof.mode == "emulator":
        return _emulator_fetch_snapshot(prof, device_id, timeout=timeout)

    # Backward-compatibility path for tests/manual profile injection. Stored
    # profiles are normalized to webportal mode in `resolve_profile`.
    if prof.mode == "native":
        native_exc: Exception | None = None
        try:
            return _native_fetch_snapshot(prof, device_id, timeout=timeout)
        except EufyCaptchaRequired:
            solved = solve_cloud_captcha(
                profile,
                timeout=min(timeout, 10.0),
                max_rounds=3,
            )
            if solved.get("solved"):
                return _native_fetch_snapshot(prof, device_id, timeout=timeout)
            native_exc = EufyCloudError(
                "Native mode blocked by captcha (auto-solve failed)."
            )
        except EufyCloudError as exc:
            native_exc = exc

        native_reason = str(native_exc or "").lower()
        allow_webportal_fallback = bool(
            native_exc
            and (
                "no usable snapshot or stream url" in native_reason
                or "captcha" in native_reason
            )
        )
        if allow_webportal_fallback and prof.webportal_url:
            try:
                return _webportal_fetch_snapshot(prof, device_id, timeout=timeout)
            except Exception as web_exc:
                if native_exc:
                    raise EufyCloudError(
                        f"Native snapshot failed ({native_exc}); web portal fallback failed ({web_exc})"
                    ) from web_exc
                raise
        if native_exc:
            raise native_exc
        raise EufyCloudError("Native snapshot failed")

    if prof.mode == "webportal":
        return _webportal_fetch_snapshot(prof, device_id, timeout=timeout)

    ensure_bridge_running(profile)

    url = _snapshot_url_for_device(prof, device_id)

    try:
        resp = requests.get(
            url,
            headers=_headers(prof),
            timeout=timeout,
            verify=prof.verify_tls,
        )
    except Exception as exc:
        raise EufyCloudError(f"Bridge snapshot request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise EufyCloudError(f"Bridge snapshot returned HTTP {resp.status_code}")

    content_type = str(resp.headers.get("Content-Type") or "").split(";", 1)[0].strip()
    if content_type.startswith("image/"):
        return resp.content, content_type or "image/jpeg"

    # Some bridges return JSON indirection (`{"snapshot_url":"..."}` or base64).
    try:
        payload = resp.json()
    except Exception as exc:
        raise EufyCloudError(
            f"Bridge snapshot response is not an image (content-type={content_type or 'unknown'})"
        ) from exc

    if not isinstance(payload, dict):
        raise EufyCloudError("Bridge snapshot JSON payload is invalid")

    b64 = str(
        payload.get("image_base64")
        or payload.get("snapshot_base64")
        or payload.get("jpeg_base64")
        or ""
    ).strip()
    if b64:
        try:
            return base64.b64decode(b64), "image/jpeg"
        except Exception as exc:
            raise EufyCloudError("Invalid snapshot base64 payload") from exc

    redirect_url = str(
        payload.get("snapshot_url")
        or payload.get("image_url")
        or payload.get("url")
        or ""
    ).strip()
    if redirect_url:
        if redirect_url.startswith("/"):
            redirect_url = _join_url(prof.bridge_url, redirect_url)
        try:
            proxied = requests.get(
                redirect_url,
                headers=_headers(prof),
                timeout=timeout,
                verify=prof.verify_tls,
            )
        except Exception as exc:
            raise EufyCloudError(f"Snapshot redirect fetch failed: {exc}") from exc
        if proxied.status_code >= 400:
            raise EufyCloudError(
                f"Snapshot redirect returned HTTP {proxied.status_code}"
            )
        proxied_type = (
            str(proxied.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        )
        if proxied_type.startswith("image/"):
            return proxied.content, proxied_type or "image/jpeg"
        raise EufyCloudError("Snapshot redirect did not return an image")

    raise EufyCloudError("Bridge snapshot payload did not include image data")
