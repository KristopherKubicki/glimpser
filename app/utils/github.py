"""Query release information from GitHub for update checks.

The helper functions fetch the latest tagged version of the project and
compare it against a supplied version string.  Network failures are
logged and cached results are reused to avoid hitting rate limits.  The
module is used by the auto-update mechanism and for displaying upgrade
notifications.
"""

import logging
import re
from functools import lru_cache

import requests

GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/KristopherKubicki/glimpser/releases/latest"
)


def _parse_version(version: str) -> list[int]:
    """Return version components as integers."""
    return [int(part) for part in re.findall(r"\d+", str(version))]


@lru_cache(maxsize=1)
def get_latest_release_version(timeout: int = 3) -> str | None:
    """Return the latest release version from GitHub or ``None`` on failure."""
    try:
        resp = requests.get(GITHUB_RELEASES_URL, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            tag = data.get("tag_name", "")
            return tag.lstrip("v")
    except Exception as exc:  # pragma: no cover - log and ignore failures
        logging.debug("Failed to fetch release info: %s", exc)
    return None


def is_update_available(current_version: str) -> bool:
    """Return ``True`` if a newer release exists on GitHub."""
    latest = get_latest_release_version()
    if not latest:
        return False
    try:
        return _parse_version(latest) > _parse_version(current_version)
    except Exception:
        return False
