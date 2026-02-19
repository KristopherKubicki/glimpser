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
from urllib.parse import quote, urlencode

import requests
from itsdangerous import BadData, URLSafeTimedSerializer

from app import config
from app.utils.google_sdm_profiles import resolve_profile

_PCM_AUTH_BASE = "https://nestservices.google.com/partnerconnections"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SDM_BASE = "https://smartdevicemanagement.googleapis.com/v1"

# Scope required for the SDM API.
_SDM_SCOPE = "https://www.googleapis.com/auth/sdm.service"


@dataclass(frozen=True)
class SdmRtspStream:
    rtsp_url: str
    expires_at: datetime.datetime | None


@dataclass(frozen=True)
class SdmWebRtcStream:
    answer_sdp: str
    media_session_id: str
    expires_at: datetime.datetime | None


class GoogleSdmError(RuntimeError):
    pass


_access_lock = threading.Lock()
_access_token: dict[str, str] = {}
_access_expires_at: dict[str, datetime.datetime] = {}

_resolve_lock = threading.Lock()
_resolved_rtsp_cache: dict[str, SdmRtspStream] = {}
_resolved_rtsp_reverse: dict[str, str] = {}

_PREVIEW_TOKEN_SALT = "google-sdm-webrtc-preview-v1"


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _profile(name: str | None):
    prof = resolve_profile(name)
    if not prof:
        raise GoogleSdmError("Google SDM profile is not configured")
    return prof


def configured(profile: str | None = None) -> bool:
    prof = resolve_profile(profile)
    if not prof:
        return False
    return bool(
        prof.client_id and prof.client_secret and prof.project_id and prof.redirect_uri
    )


def build_oauth_authorize_url(state: str, profile: str | None = None) -> str:
    """Return the OAuth authorize URL."""

    if not configured(profile):
        raise GoogleSdmError("Google SDM is not configured")

    # Device Access uses Partner Connections Manager (PCM) for account linking.
    # Using the standard Google OAuth endpoint will mint a token with the SDM
    # scope, but the token will not be associated with any enterprise until the
    # user grants structure/device permissions in PCM.
    project_id = _profile(profile).project_id
    if not project_id:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    params = {
        "client_id": _profile(profile).client_id,
        "redirect_uri": _profile(profile).redirect_uri,
        "response_type": "code",
        "scope": _SDM_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        # PCM is still OAuth under the hood, so we keep `state` to prevent CSRF
        # and map the callback back to a configured Glimpser profile.
        "state": state,
    }
    auth_url = f"{_PCM_AUTH_BASE}/{project_id}/auth"
    return f"{auth_url}?{urlencode(params)}"


def exchange_code_for_refresh_token(
    code: str, profile: str | None = None
) -> tuple[str, str, int]:
    """Exchange an OAuth `code` for refresh+access tokens."""

    if not configured(profile):
        raise GoogleSdmError("Google SDM is not configured")

    data = {
        "client_id": _profile(profile).client_id,
        "client_secret": _profile(profile).client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _profile(profile).redirect_uri,
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


def _refresh_access_token(profile: str | None = None) -> tuple[str, int]:
    refresh = _profile(profile).refresh_token
    if not refresh:
        raise GoogleSdmError("Missing GOOGLE_SDM_REFRESH_TOKEN")

    data = {
        "client_id": _profile(profile).client_id,
        "client_secret": _profile(profile).client_secret,
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


def access_token(profile: str | None = None) -> str:
    """Return a valid access token, refreshing if needed."""

    global _access_token, _access_expires_at

    with _access_lock:
        key = str(profile or "default")
        token = _access_token.get(key)
        exp = _access_expires_at.get(key)
        if token and exp:
            # Refresh a bit early to avoid edge expiry.
            if exp - _now_utc() > datetime.timedelta(seconds=30):
                return token

        access, expires_in = _refresh_access_token(profile)
        _access_token[key] = access
        _access_expires_at[key] = _now_utc() + datetime.timedelta(
            seconds=int(expires_in)
        )
        return access


def clear_cached_tokens() -> None:
    """Clear cached access tokens and resolved RTSP URLs.

    Useful after disconnecting a Google account or rotating credentials.
    """

    global _access_token, _access_expires_at
    with _access_lock:
        _access_token.clear()
        _access_expires_at.clear()

    with _resolve_lock:
        _resolved_rtsp_cache.clear()
        _resolved_rtsp_reverse.clear()


def _auth_headers(profile: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token(profile)}"}


def _device_name(device_id: str, profile: str | None = None) -> str:
    project = _profile(profile).project_id
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")
    device_id = str(device_id or "").strip()
    if not device_id:
        raise GoogleSdmError("Missing SDM device id")
    return f"enterprises/{project}/devices/{device_id}"


def list_devices(profile: str | None = None) -> list[dict[str, Any]]:
    project = _profile(profile).project_id
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    url = f"{_SDM_BASE}/enterprises/{project}/devices"
    resp = requests.get(url, headers=_auth_headers(profile), timeout=30)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"SDM list devices failed: {resp.status_code} {resp.text[:200]}"
        )
    payload = resp.json()
    return list(payload.get("devices") or [])


def generate_rtsp_stream(device_name: str, profile: str | None = None) -> SdmRtspStream:
    """Generate an RTSP stream URL for a given SDM `device_name`.

    `device_name` should be the full SDM resource name, for example:
    `enterprises/<project_id>/devices/<device_id>`.
    """

    project = _profile(profile).project_id
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    if "/devices/" not in device_name:
        raise GoogleSdmError("device_name does not look like an SDM device resource")

    url = f"{_SDM_BASE}/{device_name}:executeCommand"
    payload = {
        "command": "sdm.devices.commands.CameraLiveStream.GenerateRtspStream",
        "params": {},
    }

    resp = requests.post(url, json=payload, headers=_auth_headers(profile), timeout=30)
    if resp.status_code != 200:
        error_msg = ""
        try:
            payload = resp.json()
            error_msg = str((payload.get("error") or {}).get("message") or "").strip()
        except Exception:
            error_msg = ""

        if "not supporting RTSP protocol" in error_msg:
            raise GoogleSdmError(
                "SDM camera is WEB_RTC-only; RTSP snapshots are not available"
            )

        raise GoogleSdmError(
            f"SDM generate stream failed: {resp.status_code} {resp.text[:200]}"
        )

    data = resp.json()
    results = data.get("results") or {}
    stream_urls = results.get("streamUrls") or {}
    rtsp_url = results.get("rtspUrl") or stream_urls.get("rtspUrl")
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


def generate_webrtc_stream(
    device_name: str, offer_sdp: str, profile: str | None = None
) -> SdmWebRtcStream:
    """Generate a WebRTC answer/session for a given SDM `device_name`."""

    if "/devices/" not in str(device_name):
        raise GoogleSdmError("device_name does not look like an SDM device resource")

    raw_offer = str(offer_sdp or "")
    if not raw_offer.strip():
        raise GoogleSdmError("Missing WebRTC offer SDP")
    # SDM requires CRLF-terminated SDP. Avoid `.strip()` here because it drops
    # trailing CRLF and causes SDM to reject otherwise-valid offers.
    normalized = raw_offer.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line for line in normalized.split("\n") if line != ""]
    offer_sdp = "\r\n".join(lines) + "\r\n"

    url = f"{_SDM_BASE}/{device_name}:executeCommand"
    payload = {
        "command": "sdm.devices.commands.CameraLiveStream.GenerateWebRtcStream",
        "params": {"offerSdp": offer_sdp},
    }

    resp = requests.post(url, json=payload, headers=_auth_headers(profile), timeout=30)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"SDM generate WebRTC failed: {resp.status_code} {resp.text[:200]}"
        )

    data = resp.json()
    results = data.get("results") or {}
    answer_sdp = str(results.get("answerSdp") or "").strip()
    media_session_id = str(results.get("mediaSessionId") or "").strip()
    expires_at_raw = results.get("expiresAt")
    expires_at = None
    if expires_at_raw:
        try:
            expires_at = datetime.datetime.fromisoformat(
                str(expires_at_raw).replace("Z", "+00:00")
            )
        except Exception:
            expires_at = None

    if not answer_sdp or not media_session_id:
        raise GoogleSdmError("SDM did not return WebRTC answer/session")

    return SdmWebRtcStream(
        answer_sdp=answer_sdp,
        media_session_id=media_session_id,
        expires_at=expires_at,
    )


def extend_webrtc_stream(
    device_name: str, media_session_id: str, profile: str | None = None
) -> datetime.datetime | None:
    """Extend an SDM WebRTC stream session."""

    if "/devices/" not in str(device_name):
        raise GoogleSdmError("device_name does not look like an SDM device resource")
    media_session_id = str(media_session_id or "").strip()
    if not media_session_id:
        raise GoogleSdmError("Missing media session id")

    url = f"{_SDM_BASE}/{device_name}:executeCommand"
    payload = {
        "command": "sdm.devices.commands.CameraLiveStream.ExtendWebRtcStream",
        "params": {"mediaSessionId": media_session_id},
    }

    resp = requests.post(url, json=payload, headers=_auth_headers(profile), timeout=20)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"SDM extend WebRTC failed: {resp.status_code} {resp.text[:200]}"
        )

    expires_at_raw = (resp.json().get("results") or {}).get("expiresAt")
    if not expires_at_raw:
        return None
    try:
        return datetime.datetime.fromisoformat(
            str(expires_at_raw).replace("Z", "+00:00")
        )
    except Exception:
        return None


def stop_webrtc_stream(
    device_name: str, media_session_id: str, profile: str | None = None
) -> None:
    """Stop an SDM WebRTC stream session."""

    if "/devices/" not in str(device_name):
        raise GoogleSdmError("device_name does not look like an SDM device resource")
    media_session_id = str(media_session_id or "").strip()
    if not media_session_id:
        raise GoogleSdmError("Missing media session id")

    url = f"{_SDM_BASE}/{device_name}:executeCommand"
    payload = {
        "command": "sdm.devices.commands.CameraLiveStream.StopWebRtcStream",
        "params": {"mediaSessionId": media_session_id},
    }
    resp = requests.post(url, json=payload, headers=_auth_headers(profile), timeout=20)
    if resp.status_code != 200:
        raise GoogleSdmError(
            f"SDM stop WebRTC failed: {resp.status_code} {resp.text[:200]}"
        )


def parse_sdm_url(url: str) -> tuple[str | None, str | None]:
    """Return (profile, device_id) when `url` is `sdm://...`.

    Supported forms:
    - `sdm://<device_id>` (legacy single-profile)
    - `sdm://<profile>/<device_id>` (multi-project)
    """

    if not url or not url.startswith("sdm://"):
        return None, None

    rest = url[len("sdm://") :].strip("/")
    if not rest:
        return None, None

    parts = [p for p in rest.split("/") if p]
    if len(parts) == 1:
        return None, parts[0]
    return parts[0], parts[1]


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

    profile, device_id = parse_sdm_url(stable_sdm_url)
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

    project = _profile(profile).project_id
    if not project:
        raise GoogleSdmError("Missing GOOGLE_SDM_PROJECT_ID")

    device_name = f"enterprises/{project}/devices/{device_id}"
    stream = generate_rtsp_stream(device_name, profile)

    with _resolve_lock:
        _resolved_rtsp_cache[stable_sdm_url] = stream
        _resolved_rtsp_reverse[stream.rtsp_url] = stable_sdm_url

    logging.info(
        "SDM stream resolved: %s -> rtsp (expires=%s)",
        stable_sdm_url,
        stream.expires_at,
    )
    return stream.rtsp_url


def webrtc_device_name_from_stable_url(stable_sdm_url: str) -> tuple[str, str]:
    """Resolve `sdm://...` into `(profile, device_name)` for WebRTC commands."""

    profile, device_id = parse_sdm_url(stable_sdm_url)
    profile = profile or "default"
    if not device_id:
        raise GoogleSdmError("Invalid SDM URL: missing device id")
    return profile, _device_name(device_id, profile)


def issue_webrtc_preview_token(profile: str, device_id: str) -> str:
    """Issue a short signed token for internal WebRTC preview/auth."""

    signer = URLSafeTimedSerializer(str(config.SECRET_KEY), salt=_PREVIEW_TOKEN_SALT)
    payload = {"p": str(profile or "default"), "d": str(device_id or "")}
    return str(signer.dumps(payload))


def verify_webrtc_preview_token(
    token: str, *, max_age_seconds: int = 600
) -> tuple[str, str] | None:
    """Validate a signed WebRTC preview token.

    Returns `(profile, device_id)` when valid, else `None`.
    """

    token = str(token or "").strip()
    if not token:
        return None
    signer = URLSafeTimedSerializer(str(config.SECRET_KEY), salt=_PREVIEW_TOKEN_SALT)
    try:
        data = signer.loads(token, max_age=max_age_seconds)
    except BadData:
        return None
    if not isinstance(data, dict):
        return None
    profile = str(data.get("p") or "default").strip() or "default"
    device_id = str(data.get("d") or "").strip()
    if not device_id:
        return None
    return profile, device_id


def build_webrtc_preview_url(stable_sdm_url: str) -> str | None:
    """Build a local preview URL for SDM WEB_RTC captures.

    This URL is signed and intended for internal headless browser snapshots.
    """

    profile, device_id = parse_sdm_url(stable_sdm_url)
    if not device_id:
        return None
    profile = profile or "default"
    token = issue_webrtc_preview_token(profile, device_id)

    if bool(getattr(config, "HTTPS_ENABLED", False)) and bool(
        getattr(config, "HTTPS_ONLY", False)
    ):
        scheme = "https"
        port = int(getattr(config, "HTTPS_PORT", 8443))
    else:
        scheme = "http"
        port = int(getattr(config, "PORT", 8082))

    return (
        f"{scheme}://127.0.0.1:{port}/integrations/google/webrtc/preview"
        f"?profile={quote(profile, safe='')}"
        f"&device_id={quote(device_id, safe='')}"
        f"&token={quote(token, safe='')}"
    )
