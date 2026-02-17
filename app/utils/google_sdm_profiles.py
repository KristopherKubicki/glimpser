"""Google SDM profile storage helpers.

We support multiple Google Device Access (SDM) "projects" (enterprises) by
storing a JSON blob in the settings table. This keeps Glimpser self-contained
while allowing users with multiple homes/projects to connect each separately.

Settings
--------
- GOOGLE_SDM_PROFILES: JSON dict of profiles

Example:
{
  "argyle": {
    "project_id": "5be...",
    "client_id": "...apps.googleusercontent.com",
    "client_secret": "...",
    "redirect_uri": "http://192.168.2.137:8082/integrations/google/callback",
    "refresh_token": "..."
  },
  "halsted": { ... }
}

Backward compatibility
----------------------
If GOOGLE_SDM_PROFILES is missing/empty, Glimpser falls back to the legacy
single-project settings in app.config:
- GOOGLE_SDM_PROJECT_ID, GOOGLE_SDM_CLIENT_ID, GOOGLE_SDM_CLIENT_SECRET,
  GOOGLE_SDM_REDIRECT_URI, GOOGLE_SDM_REFRESH_TOKEN
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app import config


@dataclass(frozen=True)
class SdmProfile:
    name: str
    project_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    refresh_token: str = ""


def _raw_profiles() -> dict:
    raw = config.get_setting("GOOGLE_SDM_PROFILES", "") or ""
    raw = str(raw).strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_profile_names() -> list[str]:
    names = sorted(str(k) for k in _raw_profiles().keys())
    return [n for n in names if n]


def get_profile(name: str | None) -> SdmProfile | None:
    if not name:
        return None
    data = _raw_profiles().get(name)
    if not isinstance(data, dict):
        return None

    project_id = str(data.get("project_id") or "").strip()
    client_id = str(data.get("client_id") or "").strip()
    client_secret = str(data.get("client_secret") or "").strip()
    redirect_uri = str(data.get("redirect_uri") or "").strip()
    refresh_token = str(data.get("refresh_token") or "").strip()

    if not (project_id and client_id and client_secret and redirect_uri):
        return None

    return SdmProfile(
        name=str(name),
        project_id=project_id,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        refresh_token=refresh_token,
    )


def legacy_profile() -> SdmProfile | None:
    project_id = str(config.get_setting("GOOGLE_SDM_PROJECT_ID", "") or "").strip()
    client_id = str(config.get_setting("GOOGLE_SDM_CLIENT_ID", "") or "").strip()
    client_secret = str(
        config.get_setting("GOOGLE_SDM_CLIENT_SECRET", "") or ""
    ).strip()
    redirect_uri = str(config.get_setting("GOOGLE_SDM_REDIRECT_URI", "") or "").strip()
    refresh_token = str(
        config.get_setting("GOOGLE_SDM_REFRESH_TOKEN", "") or ""
    ).strip()

    if not (project_id and client_id and client_secret and redirect_uri):
        return None

    return SdmProfile(
        name="default",
        project_id=project_id,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        refresh_token=refresh_token,
    )


def resolve_profile(name: str | None) -> SdmProfile | None:
    # Prefer explicit profile
    prof = get_profile(name)
    if prof:
        return prof

    # Fall back to legacy single-profile config
    return legacy_profile()
