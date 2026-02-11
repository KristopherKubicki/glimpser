"""Check network connectivity using both HTTP and TCP probes.

Utilities in this module attempt to reach well known endpoints to judge
whether the system has outbound network access.  These checks avoid
network operations in tests and handle custom hosts provided via
environment variables.
"""

import ipaddress
import logging
import os
import socket
import time

from app.utils.api_utils import request_with_retry

DEFAULT_GRACE_SECONDS = 300
OFFLINE_LOG_THROTTLE_SECONDS = 300

_state: dict[str, float | str | None] = {
    "last_online_time": None,
    "last_online_reason": None,
    "last_offline_log": None,
    "last_dns_ok_time": None,
    "last_wan_ok_time": None,
    "last_lan_ok_time": None,
    "last_dns_ok_reason": None,
    "last_wan_ok_reason": None,
    "last_lan_ok_reason": None,
}


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_private_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _parse_target(target: str, default_port: int) -> tuple[str, int]:
    """Return ``(host, port)`` tuple for ``target``."""
    if ":" in target:
        host, p = target.rsplit(":", 1)
        try:
            return host, int(p)
        except ValueError:
            return host, default_port
    return target, default_port


def _check_url(url: str, timeout: int) -> bool:
    """Return ``True`` if ``url`` responds to a HEAD request."""
    try:
        resp = request_with_retry("HEAD", url, timeout=timeout)
        return bool(resp and resp.ok)
    except Exception as exc:  # pragma: no cover - network depends on environment
        logging.debug("offline check failed for %s: %s", url, exc)
        return False


def _try_connect(target: str, timeout: int, default_port: int) -> bool:
    """Return ``True`` if ``target`` can be reached via TCP."""
    host, port = _parse_target(target, default_port)
    try:
        socket.create_connection((host, port), timeout=timeout)
        return True
    except OSError as exc:  # pragma: no cover - network depends on environment
        logging.debug("offline check failed for %s:%s: %s", host, port, exc)
    return False


def _get_test_hosts():
    """Return list of hosts to probe for network connectivity."""
    return os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1").split(",")


def _get_lan_test_hosts() -> list[str]:
    return _parse_list(os.getenv("LAN_TEST_HOSTS", ""))


def _get_dns_test_hosts() -> list[str]:
    return _parse_list(os.getenv("DNS_TEST_HOSTS", "1.1.1.1,8.8.8.8"))


def _offline_grace_seconds() -> int:
    try:
        return max(
            int(os.getenv("OFFLINE_GRACE_SECONDS", str(DEFAULT_GRACE_SECONDS))), 0
        )
    except ValueError:
        return DEFAULT_GRACE_SECONDS


def _grace_seconds(env_name: str, fallback: int) -> int:
    try:
        return max(int(os.getenv(env_name, str(fallback))), 0)
    except ValueError:
        return fallback


def _maybe_log_offline(message: str) -> None:
    now = time.time()
    last_log = _state["last_offline_log"]
    if last_log and now - last_log < OFFLINE_LOG_THROTTLE_SECONDS:
        return
    _state["last_offline_log"] = now
    logging.warning(message)


def is_system_online(timeout: int = 3) -> bool:
    """Return ``True`` if the system can reach any configured test endpoint."""
    try:
        default_port = int(os.getenv("ONLINE_TEST_PORT", "443"))
        urls = [
            u.strip()
            for u in os.getenv(
                "ONLINE_TEST_URLS",
                "https://connectivitycheck.gstatic.com/generate_204",
            ).split(",")
            if u.strip()
        ]

        # HTTP(S) reachability check similar to Android/iOS captive portal detection
        for url in urls:
            if _check_url(url, timeout):
                _state["last_online_time"] = time.time()
                _state["last_online_reason"] = f"url:{url}"
                return True

        hosts = [h.strip() for h in _get_test_hosts() if h.strip()]
        if not hosts and not urls:
            logging.warning("offline check failed: no hosts configured")
            return False

        for host in hosts:
            if _try_connect(host, timeout, default_port):
                _state["last_online_time"] = time.time()
                _state["last_online_reason"] = f"tcp:{host}"
                return True

        grace = _offline_grace_seconds()
        last_online_time = _state["last_online_time"]
        if last_online_time and time.time() - last_online_time < grace:
            logging.info(
                "offline check failed; using grace window (%ds) from %s",
                grace,
                _state["last_online_reason"] or "unknown",
            )
            return True
        _maybe_log_offline("offline check failed: all hosts unreachable")
        return False

    except Exception as exc:  # pragma: no cover - unexpected environment failure
        logging.debug("is_system_online error: %s", exc)
        return False


def network_state(timeout: int = 3) -> dict[str, object]:  # noqa: PLR0912
    """Return connectivity state for LAN, DNS, and WAN probes."""
    now = time.time()
    lan_ok = False
    dns_ok = False
    wan_ok = False

    lan_hosts = _get_lan_test_hosts()
    if not lan_hosts:
        # Default to LAN OK when no explicit probe is configured. LAN reachability
        # is ultimately enforced by per-host connection attempts (and backoff),
        # but we should not globally disable all private-IP captures by default.
        lan_ok = True
        _state["last_lan_ok_time"] = now
        _state["last_lan_ok_reason"] = "not_configured"
    else:
        for host in lan_hosts:
            if _try_connect(host, timeout, 80):
                lan_ok = True
                _state["last_lan_ok_time"] = now
                _state["last_lan_ok_reason"] = f"tcp:{host}"
                break

    dns_hosts = _get_dns_test_hosts()
    for host in dns_hosts:
        try:
            socket.getaddrinfo(host, 53)
            dns_ok = True
            _state["last_dns_ok_time"] = now
            _state["last_dns_ok_reason"] = f"dns:{host}"
            break
        except OSError:
            continue

    wan_urls = _parse_list(
        os.getenv(
            "ONLINE_TEST_URLS",
            "https://connectivitycheck.gstatic.com/generate_204",
        )
    )
    for url in wan_urls:
        if _check_url(url, timeout):
            wan_ok = True
            _state["last_wan_ok_time"] = now
            _state["last_wan_ok_reason"] = f"url:{url}"
            break
    if not wan_ok:
        wan_hosts = _parse_list(os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1"))
        wan_port = int(os.getenv("ONLINE_TEST_PORT", "443"))
        for host in wan_hosts:
            if _try_connect(host, timeout, wan_port):
                wan_ok = True
                _state["last_wan_ok_time"] = now
                _state["last_wan_ok_reason"] = f"tcp:{host}"
                break

    dns_grace = _grace_seconds("DNS_GRACE_SECONDS", DEFAULT_GRACE_SECONDS)
    wan_grace = _grace_seconds("WAN_GRACE_SECONDS", DEFAULT_GRACE_SECONDS)
    lan_grace = _grace_seconds("LAN_GRACE_SECONDS", DEFAULT_GRACE_SECONDS)

    last_dns_ok_time = _state["last_dns_ok_time"]
    last_wan_ok_time = _state["last_wan_ok_time"]
    last_lan_ok_time = _state["last_lan_ok_time"]
    if not dns_ok and last_dns_ok_time and now - last_dns_ok_time < dns_grace:
        dns_ok = True
    if not wan_ok and last_wan_ok_time and now - last_wan_ok_time < wan_grace:
        wan_ok = True
    if not lan_ok and last_lan_ok_time and now - last_lan_ok_time < lan_grace:
        lan_ok = True

    return {
        "lan_ok": lan_ok,
        "dns_ok": dns_ok,
        "wan_ok": wan_ok,
        "lan_reason": _state["last_lan_ok_reason"],
        "dns_reason": _state["last_dns_ok_reason"],
        "wan_reason": _state["last_wan_ok_reason"],
        "timestamp": now,
    }
