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
import json
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import requests
from itsdangerous import BadData, URLSafeSerializer

from app import config

_SNAPSHOT_TOKEN_SALT = "eufy-cloud-snapshot-v1"
_EUFY_API_BASE = "https://mysecurity.eufylife.com/api/v1"
_NATIVE_REFRESH_GRACE_SECONDS = 60.0

_NATIVE_SESSION_LOCK = threading.Lock()
_NATIVE_SESSIONS: dict[str, dict[str, object]] = {}


class EufyCloudError(RuntimeError):
    """Raised when Eufy cloud integration calls fail."""


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
    if mode not in {"external", "native"}:
        mode = "external"

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
    )


def configured(profile: str = "default") -> bool:
    """Return whether a profile has enough config to capture snapshots."""

    prof = resolve_profile(profile)
    if prof is None:
        return False
    if prof.mode == "native":
        return bool(prof.native_email and prof.native_password)
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


def _native_session(profile: EufyCloudProfile, *, timeout: float) -> tuple[str, str]:
    now = time.time()
    with _NATIVE_SESSION_LOCK:
        cached = _NATIVE_SESSIONS.get(profile.name)
        if isinstance(cached, dict):
            token = str(cached.get("token") or "").strip()
            api_base = str(cached.get("api_base") or _EUFY_API_BASE).strip()
            expires_at = float(cached.get("expires_at") or 0)
            if token and api_base and expires_at > now + _NATIVE_REFRESH_GRACE_SECONDS:
                return token, api_base

    if not profile.native_email or not profile.native_password:
        raise EufyCloudError(
            f"Eufy profile '{profile.name}' missing cloud email/password"
        )

    login_payload = {
        "email": profile.native_email,
        "password": profile.native_password,
    }

    try:
        resp = requests.post(
            f"{_EUFY_API_BASE}/passport/login",
            json=login_payload,
            timeout=timeout,
            verify=profile.verify_tls,
        )
    except Exception as exc:
        raise EufyCloudError(f"Eufy cloud login request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise EufyCloudError(f"Eufy cloud login returned HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except Exception as exc:
        raise EufyCloudError("Eufy cloud login returned invalid JSON") from exc

    code = _native_error_code(payload)
    if code != 0:
        msg = _native_error_text(payload)
        raise EufyCloudError(f"Eufy cloud login failed ({code}): {msg}")

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise EufyCloudError("Eufy cloud login response missing data payload")

    token = str(data.get("auth_token") or "").strip()
    if not token:
        raise EufyCloudError("Eufy cloud login succeeded but auth token missing")

    domain = str(data.get("domain") or "").strip()
    api_base = _EUFY_API_BASE
    if domain:
        api_base = f"https://{domain}/v1"

    try:
        expires_at = float(data.get("token_expires_at") or 0)
    except Exception:
        expires_at = 0
    if expires_at <= now:
        expires_at = now + 1800

    with _NATIVE_SESSION_LOCK:
        _NATIVE_SESSIONS[profile.name] = {
            "token": token,
            "api_base": api_base,
            "expires_at": expires_at,
        }

    return token, api_base


def _native_request(
    profile: EufyCloudProfile,
    endpoint: str,
    *,
    payload: dict | None = None,
    timeout: float,
    retry: bool = True,
) -> dict:
    token, api_base = _native_session(profile, timeout=timeout)
    url = f"{api_base.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        resp = requests.post(
            url,
            headers={"x-auth-token": token},
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

    return body if isinstance(body, dict) else {}


def _native_snapshot_url(device: dict) -> str:
    if not isinstance(device, dict):
        return ""
    url = str(
        device.get("cover_path")
        or device.get("picture_url")
        or device.get("snapshot_url")
        or ""
    ).strip()
    if url.startswith("//"):
        return "https:" + url
    return url


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
    payload = _native_request(profile, "app/get_devs_list", timeout=timeout)
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
        out.append(
            {
                "device_id": did,
                "name": name,
                "online": _native_online(item),
                "snapshot": bool(_native_snapshot_url(item)),
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

    token, _api_base = _native_session(profile, timeout=timeout)
    last_error = ""
    for headers in (
        {"x-auth-token": token},
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
    payload = _native_request(profile, "app/get_devs_list", timeout=timeout)
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

    image_url = _native_snapshot_url(target)
    if not image_url:
        raise EufyCloudError(
            f"Eufy cloud device '{did}' has no snapshot/cover URL in API response"
        )

    return _native_fetch_image(profile, image_url, timeout=timeout)


def list_devices(profile: str = "default", *, timeout: float = 12.0) -> list[dict]:
    """List devices for a configured Eufy profile."""

    prof = resolve_profile(profile)
    if not prof:
        raise EufyCloudError(f"Eufy cloud profile '{profile}' is not configured")

    if prof.mode == "native":
        return _native_list_devices(prof, timeout=timeout)

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

    if prof.mode == "native":
        return _native_fetch_snapshot(prof, device_id, timeout=timeout)

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
