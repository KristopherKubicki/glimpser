import logging
import os
import subprocess
import sys

import requests

from app.utils.github import get_latest_release_version

GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/KristopherKubicki/glimpser/releases/latest"
)
GITHUB_STATUS_URL = (
    "https://api.github.com/repos/KristopherKubicki/glimpser/commits/{sha}/status"
)


def _ci_green(commit: str) -> bool:
    """Return ``True`` if the commit's CI status is green."""
    try:
        resp = requests.get(GITHUB_STATUS_URL.format(sha=commit), timeout=5)
        if resp.status_code == 200:
            return resp.json().get("state") == "success"
    except Exception as exc:  # pragma: no cover - log and ignore failures
        logging.debug("CI status check failed: %s", exc)
    return False


def _download_and_install(version: str) -> bool:
    """Install the specified package version via ``pip``."""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", f"glimpser=={version}"]
        )
        return True
    except subprocess.CalledProcessError as exc:
        logging.error("Auto-update installation failed: %s", exc)
        return False


def check_for_update() -> None:
    """Check GitHub for a new release and update if allowed."""
    from app import config

    branch = config.AUTO_UPDATE_BRANCH
    if branch == "None":
        return

    latest = get_latest_release_version()
    if not latest or latest == config.VERSION:
        return

    try:
        resp = requests.get(GITHUB_RELEASES_URL, timeout=5)
        if resp.status_code != 200:
            return
        release = resp.json()
        target_branch = release.get("target_commitish", "").lower()
        commit_sha = release.get("target_commitish", "")
        if branch.lower() != target_branch:
            return
        if not _ci_green(commit_sha):
            logging.info("CI status for %s not green", commit_sha)
            return
        if _download_and_install(latest):
            logging.warning("Auto-updating to %s", latest)
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as exc:  # pragma: no cover - log and ignore failures
        logging.debug("Auto-update check failed: %s", exc)
