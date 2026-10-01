"""Exercise maintainer scripts in an isolated mount namespace, never the host."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def package_sandbox(tmp_path):
    if not shutil.which("bwrap"):
        pytest.skip("bubblewrap required for isolated maintainer-script tests")
    probe = subprocess.run(
        ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "/bin/true"],
        capture_output=True,
    )
    if probe.returncode:
        pytest.skip("mount namespaces unavailable")
    binary = tmp_path / "bin"
    binary.mkdir()
    app = tmp_path / "app"
    venv = app / ".venv/bin"
    venv.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    systemd = tmp_path / "systemd"
    systemd.mkdir()
    log = tmp_path / "calls"
    fake = """#!/bin/sh
set -eu
name=${0##*/}
echo "$name $*" >> "$TEST_LOG"
case "$name" in
    python3) if [ "$#" = 1 ]; then cat >/dev/null; echo 0.12.21; fi ;;
    uv) exit "${FAIL_SYNC:-0}" ;;
    getent) exit 2 ;;
    deb-systemd-helper) if [ "${2:-}" = was-enabled ]; then exit "${WAS_DISABLED:-0}"; fi ;;
esac
"""
    for name in (
        "python3",
        "install",
        "chown",
        "getent",
        "adduser",
        "deb-systemd-helper",
        "deb-systemd-invoke",
        "systemctl",
    ):
        path = binary / name
        path.write_text(fake)
        path.chmod(0o755)
    for name in ("python", "uv"):
        path = venv / name
        path.write_text(fake)
        path.chmod(0o755)

    def run(script, phase, **env):
        log.write_text("")
        result = subprocess.run(
            [
                "bwrap",
                "--ro-bind",
                "/",
                "/",
                "--unshare-net",
                "--dev",
                "/dev",
                "--tmpfs",
                "/opt",
                "--tmpfs",
                "/var/lib",
                "--tmpfs",
                "/run",
                "--bind",
                str(tmp_path),
                str(tmp_path),
                "--bind",
                str(app),
                "/opt/glimpser",
                "--bind",
                str(home),
                "/var/lib/glimpser",
                "--bind",
                str(systemd),
                "/run/systemd/system",
                "/bin/sh",
                str(Path("debian", script).resolve()),
                phase,
            ],
            env=os.environ
            | {"PATH": f"{binary}:/usr/bin:/bin", "TEST_LOG": str(log)}
            | env,
            capture_output=True,
            text=True,
        )
        return result, log.read_text()

    return run


def test_configure_uses_locked_venv_and_policy_aware_restart(package_sandbox):
    result, calls = package_sandbox("postinst", "configure")
    assert result.returncode == 0, result.stderr
    assert "python3 -m venv /opt/glimpser/.venv" in calls
    assert "python -m pip install --disable-pip-version-check uv==0.12.21" in calls
    assert (
        "uv sync --project /opt/glimpser --locked --no-dev --no-editable --extra google-events"
        in calls
    )
    assert "python3 -m pip" not in calls
    assert "adduser --system --group" in calls
    assert "deb-systemd-invoke restart glimpser.service" in calls
    assert calls.index("uv sync") < calls.index("deb-systemd-invoke restart")
    assert "systemctl start" not in calls


def test_failed_dependency_sync_never_starts_service(package_sandbox):
    result, calls = package_sandbox("postinst", "configure", FAIL_SYNC="7")
    assert result.returncode == 7
    assert "deb-systemd-invoke" not in calls
    assert "systemctl" not in calls


def test_disabled_service_is_not_reenabled(package_sandbox):
    result, calls = package_sandbox("postinst", "configure", WAS_DISABLED="1")
    assert result.returncode == 0
    assert "deb-systemd-helper enable" not in calls


def test_abort_does_not_bootstrap_or_restart(package_sandbox):
    result, calls = package_sandbox("postinst", "abort-upgrade")
    assert result.returncode == 0
    assert not calls


def test_remove_stops_service_and_purge_preserves_runtime_data(package_sandbox):
    result, calls = package_sandbox("prerm", "remove")
    assert result.returncode == 0
    assert "deb-systemd-invoke stop glimpser.service" in calls
    result, calls = package_sandbox("postrm", "purge")
    assert result.returncode == 0
    assert "deb-systemd-helper purge glimpser.service" in calls
    assert "rm " not in calls
