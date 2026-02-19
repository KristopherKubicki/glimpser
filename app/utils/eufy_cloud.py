"""Eufy cloud bridge helpers.

Glimpser keeps Eufy cloud access enclosed by routing snapshot fetches through
local Glimpser endpoints. Templates can use stable URLs like:

    eufy://<profile>/<device_id>

At capture time those URLs are converted to signed local proxy URLs
(``/integrations/eufy/snapshot``), so camera credentials/tokens stay server-side.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import requests
from itsdangerous import BadData, URLSafeSerializer

from app import config

_SNAPSHOT_TOKEN_SALT = "eufy-cloud-snapshot-v1"


class EufyCloudError(RuntimeError):
    """Raised when Eufy cloud bridge calls fail."""


@dataclass(frozen=True)
class EufyCloudProfile:
    name: str
    bridge_url: str
    api_token: str
    devices_path: str
    snapshot_path: str
    verify_tls: bool


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
    payload = _load_profiles()
    key = str(profile or "default").strip() or "default"
    value = payload.get(key)
    if not isinstance(value, dict):
        return None

    bridge_url = str(value.get("bridge_url") or "").strip().rstrip("/")
    if not bridge_url:
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
        bridge_url=bridge_url,
        api_token=str(value.get("api_token") or "").strip(),
        devices_path=devices_path,
        snapshot_path=snapshot_path,
        verify_tls=verify_tls,
    )


def configured(profile: str = "default") -> bool:
    return resolve_profile(profile) is not None


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


def list_devices(profile: str = "default", *, timeout: float = 12.0) -> list[dict]:
    prof = resolve_profile(profile)
    if not prof:
        raise EufyCloudError(f"Eufy cloud profile '{profile}' is not configured")

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
    """Fetch a snapshot for ``device_id`` from the configured bridge profile."""

    prof = resolve_profile(profile)
    if not prof:
        raise EufyCloudError(f"Eufy cloud profile '{profile}' is not configured")

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
