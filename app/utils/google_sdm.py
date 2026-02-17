"""Google Smart Device Management (SDM) integration.

This module provides a minimal OAuth + SDM client used to:

- Authenticate with Google's Device Access / SDM API.
- Discover camera devices.
- Generate short-lived RTSP stream URLs for Nest/Google Home cameras.

Glimpser stores credentials in the settings table using uppercase keys.

Expected settings:
- GOOGLE_SDM_CLIENT_ID
- GOOGLE_SDM_CLIENT_SECRET
- GOOGLE_SDM_PROJECT_ID
- GOOGLE_SDM_REDIRECT_URI
- GOOGLE_SDM_REFRESH_TOKEN

Notes
-----
The SDM RTSP URL returned by the API is typically short-lived. Glimpser uses
stable template URLs in the form `sdm://<device_id>` and resolves them to a
fresh RTSP URL at capture time.
"""

from __future__ import annotations

import datetime
import logging
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests

from app import config

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SDM_BASE = "https://smartdevicemanagement.googleapis.com/v1"

# Scope required for the SDM API.
_SDM_SCOPE = "https://www.googleapis.com/auth/sdm.service"


@dataclass(frozen=True)
class SdmRtspStream:
    rtsp_url: str
    expires_at: datetime.datetime | None


class GoogleSdmError(RuntimeError):
    pass


_access_lock = threading.Lock()
_access_token: str | None = None
_access_expires_at: datetime.datetime | None = None

_resolve_lock = threading.Lock()
_resolved_rtsp_cache: dict[str, SdmRtspStream] = {}
_resolved_rtsp_reverse: dict[str, str] = {}


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _setting(name: str, default: str | None = None) -> str | None:
    return config.get_setting(name, default)


def configured() -> bool:
    return bool(
        _setting("GOOGLE_SDM_CLIENT_ID")
        and _setting("GOOGLE_SDM_CLIENT_SECRET")
        and _setting("GOOGLE_SDM_PROJECT_ID")
        and _setting("GOOGLE_SDM_REDIRECT_URI")
    )


def build_oauth_authorize_url(state: str) -> str:
    """Return the OAuth authorize URL."""

    if not configured():
        raise GoogleSdmError("Google SDM is not configured")

    params = {
        "client_id": _setting("GOOGLE_SDM_CLIENT_ID"),
        "redirect_uri": _setting("GOOGLE_SDM_REDIRECT_URI"),
        "response_type": "code",
        "scope": _SDM_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_refresh_token(code: str) -> tuple[str, str, int]:
    """Exchange an OAuth `code` for refresh+access tokens."""

    if not configured():
        raise GoogleSdmError("Google SDM is not configured")

    data = {
        "client_id": _setting("GOOGLE_SDM_CLIENT_ID"),
        "client_secret": _setting("GOOGLE_SDM_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _setting("GOOGLE_SDM_REDIRECT_URI"),
    }
    resp = requests.post(_TOKEN_URL, data=data, timeout=20)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"OAuth token exchange failed: {resp.status_code} {resp.text[:200]}"
        )
    payload = resp.json()
    refresh = payload.get("refresh_token")
    access = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 0)
    if not (refresh and access and expires_in):
        raise GoogleSdmError("OAuth token exchange returned incomplete payload")
    return refresh, access, expires_in


def _refresh_access_token() -> tuple[str, int]:
    refresh = _setting("GOOGLE_SDM_REFRESH_TOKEN")
    if not refresh:
        raise GoogleSdmError("Missing GOOGLE_SDM_REFRESH_TOKEN")

    data = {
        "client_id": _setting("GOOGLE_SDM_CLIENT_ID"),
        "client_secret": _setting("GOOGLE_SDM_CLIENT_SECRET"),
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }
    resp = requests.post(_TOKEN_URL, data=data, timeout=20)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"OAuth refresh failed: {resp.status_code} {resp.text[:200]}"
        )
    payload = resp.json()
    access = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 0)
    if not (access and expires_in):
        raise GoogleSdmError("OAuth refresh returned incomplete payload")
    return access, expires_in


def access_token() -> str:
    """Return a valid access token, refreshing if needed."""

    global _access_token, _access_expires_at

    with _access_lock:
        if _access_token and _access_expires_at:
            # Refresh a bit early to avoid edge expiry.
            if _access_expires_at - _now_utc() > datetime.timedelta(seconds=30):
                return _access_token

        access, expires_in = _refresh_access_token()
        _access_token = access
        _access_expires_at = _now_utc() + datetime.timedelta(seconds=int(expires_in))
        return _access_token


def clear_cached_tokens() -> None:
    """Clear cached access tokens and resolved RTSP URLs.

    Useful after disconnecting a Google account or rotating credentials.
    """

    global _access_token, _access_expires_at
    with _access_lock:
        _access_token = None
        _access_expires_at = None

    with _resolve_lock:
        _resolved_rtsp_cache.clear()
        _resolved_rtsp_reverse.clear()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token()}"}


def list_devices() -> list[dict[str, Any]]:
    project = _setting("GOOGLE_SDM_PROJECT_ID")
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    url = f"{_SDM_BASE}/enterprises/{project}/devices"
    resp = requests.get(url, headers=_auth_headers(), timeout=30)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"SDM list devices failed: {resp.status_code} {resp.text[:200]}"
        )
    payload = resp.json()
    return list(payload.get("devices") or [])


def generate_rtsp_stream(device_name: str) -> SdmRtspStream:
    """Generate an RTSP stream URL for a given SDM `device_name`.

    `device_name` should be the full SDM resource name, for example:
    `enterprises/<project_id>/devices/<device_id>`.
    """

    project = _setting("GOOGLE_SDM_PROJECT_ID")
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    if "/devices/" not in device_name:
        raise GoogleSdmError("device_name does not look like an SDM device resource")

    url = f"{_SDM_BASE}/{device_name}:executeCommand"
    payload = {
        "command": "sdm.devices.commands.CameraLiveStream.GenerateRtspStream",
        "params": {},
    }

    resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=30)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"SDM generate stream failed: {resp.status_code} {resp.text[:200]}"
        )

    data = resp.json()
    results = data.get("results") or {}
    rtsp_url = results.get("rtspUrl")
    expires_at_raw = results.get("expiresAt")

    expires_at = None
    if expires_at_raw:
        try:
            # RFC3339 / ISO8601-ish.
            expires_at = datetime.datetime.fromisoformat(
                str(expires_at_raw).replace("Z", "+00:00")
            )
        except Exception:
            expires_at = None

    if not rtsp_url:
        raise GoogleSdmError("SDM did not return an rtspUrl")

    return SdmRtspStream(rtsp_url=str(rtsp_url), expires_at=expires_at)


def parse_sdm_url(url: str) -> str | None:
    """Return the SDM device id if `url` is `sdm://<device_id>`."""

    if not url or not url.startswith("sdm://"):
        return None
    device_id = url[len("sdm://") :].strip("/")
    return device_id or None


def stable_key_for_resolved_rtsp(rtsp_url: str) -> str | None:
    """Return stable `sdm://...` key for a resolved RTSP URL (if known)."""

    if not rtsp_url:
        return None
    with _resolve_lock:
        return _resolved_rtsp_reverse.get(rtsp_url)


def resolve_sdm_to_rtsp(stable_sdm_url: str) -> str | None:
    """Resolve `sdm://<device_id>` to a fresh RTSP URL.

    Uses a small in-memory cache to avoid generating a new stream URL on every
    capture while still refreshing before expiry.
    """

    device_id = parse_sdm_url(stable_sdm_url)
    if not device_id:
        return None

    # Reuse cached stream when it's still valid for > 60s.
    with _resolve_lock:
        cached = _resolved_rtsp_cache.get(stable_sdm_url)
        if cached and cached.expires_at:
            if cached.expires_at - _now_utc() > datetime.timedelta(seconds=60):
                return cached.rtsp_url
        elif cached and cached.rtsp_url:
            # No expiry provided; reuse briefly.
            return cached.rtsp_url

    project = _setting("GOOGLE_SDM_PROJECT_ID")
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    device_name = f"enterprises/{project}/devices/{device_id}"
    stream = generate_rtsp_stream(device_name)

    with _resolve_lock:
        _resolved_rtsp_cache[stable_sdm_url] = stream
        _resolved_rtsp_reverse[stream.rtsp_url] = stable_sdm_url

    logging.info(
        "SDM stream resolved: %s -> rtsp (expires=%s)",
        stable_sdm_url,
        stream.expires_at,
    )
    return stream.rtsp_url
