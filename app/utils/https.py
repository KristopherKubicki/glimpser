"""Helpers for running Glimpser with built-in HTTPS.

Glimpser is often deployed on LAN-only hosts without an external reverse proxy.
Some integrations (notably Google OAuth) require an `https://` redirect URI, so
we optionally run a second HTTPS listener alongside the existing HTTP server.

When `HTTPS_SELF_SIGNED=True`, Glimpser will generate a self-signed certificate
at startup if the configured cert/key paths are missing.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import psutil

from app import config


def _hostnames_from_google_sdm_redirects() -> set[str]:
    raw = str(config.get_setting("GOOGLE_SDM_PROFILES", "") or "").strip()
    if not raw:
        return set()

    try:
        payload = json.loads(raw)
    except Exception:
        return set()

    if not isinstance(payload, dict):
        return set()

    names: set[str] = set()
    for data in payload.values():
        if not isinstance(data, dict):
            continue
        redirect_uri = str(data.get("redirect_uri") or "").strip()
        if not redirect_uri:
            continue
        try:
            host = urlparse(redirect_uri).hostname
        except Exception:
            host = None
        if host:
            names.add(host)
    return names


def _local_interface_ips() -> set[str]:
    ips: set[str] = set()
    try:
        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                if getattr(addr, "family", None) == socket.AF_INET:
                    ip = str(getattr(addr, "address", "") or "").strip()
                    if ip:
                        ips.add(ip)
    except Exception:
        return set()
    return ips


def collect_cert_names() -> list[str]:
    """Return a list of hostnames/IPs to include in a self-signed cert SAN."""

    names: set[str] = {"localhost", "127.0.0.1"}
    try:
        names.add(socket.gethostname())
        names.add(socket.getfqdn())
    except Exception:
        pass

    # If HOST is a concrete name (not a bind-all), include it.
    host = str(getattr(config, "HOST", "") or "").strip()
    if host and host not in {"0.0.0.0", "::"}:
        names.add(host)

    names.update(_local_interface_ips())
    names.update(_hostnames_from_google_sdm_redirects())

    extra = str(getattr(config, "HTTPS_CERT_HOSTNAMES", "") or "").strip()
    if extra:
        for part in extra.split(","):
            part = part.strip()
            if part:
                names.add(part)

    # Filter obviously invalid strings.
    cleaned: list[str] = []
    for name in sorted(names):
        if not name or " " in name:
            continue
        cleaned.append(name)
    return cleaned


def _san_extension(names: list[str]) -> tuple[str, str]:
    dns: set[str] = set()
    ips: set[str] = set()
    for name in names:
        val = str(name or "").strip()
        if not val:
            continue
        try:
            ipaddress.ip_address(val)
        except ValueError:
            dns.add(val)
        else:
            ips.add(val)

    parts: list[str] = []
    for d in sorted(dns):
        parts.append(f"DNS:{d}")
    for ip in sorted(ips):
        parts.append(f"IP:{ip}")

    # Prefer a DNS name for CN; fall back to an IP.
    primary = (sorted(dns)[:1] or sorted(ips)[:1] or ["localhost"])[0]
    return primary, ",".join(parts) or "DNS:localhost,IP:127.0.0.1"


def ensure_self_signed_cert(cert_path: str, key_path: str, names: list[str]) -> None:
    """Create a self-signed certificate if either file is missing."""

    cert = Path(cert_path)
    key = Path(key_path)
    if cert.exists() and key.exists():
        return

    cert.parent.mkdir(parents=True, exist_ok=True)
    primary, san = _san_extension(names)

    logging.warning(
        "Generating self-signed HTTPS certificate (CN=%s, SAN=%s)",
        primary,
        san,
    )

    cmd = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(key),
        "-out",
        str(cert),
        "-days",
        "825",
        "-subj",
        f"/CN={primary}",
        "-addext",
        f"subjectAltName={san}",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"openssl failed generating certificate: {stderr}") from exc

    try:
        os.chmod(key, 0o600)
    except Exception:
        pass
