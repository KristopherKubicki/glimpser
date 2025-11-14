"""Check network connectivity using both HTTP and TCP probes.

Utilities in this module attempt to reach well known endpoints to judge
whether the system has outbound network access.  These checks avoid
network operations in tests and handle custom hosts provided via
environment variables.
"""

import logging
import os
import socket

from app.utils.api_utils import request_with_retry


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
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        return True
    except OSError as exc:  # pragma: no cover - network depends on environment
        logging.debug("offline check failed for %s:%s: %s", host, port, exc)
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:  # pragma: no cover - close failures should not bubble
                logging.debug("offline check close failed for %s:%s", host, port)


def _get_test_hosts():
    """Return list of hosts to probe for network connectivity."""
    return os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1").split(",")


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
                return True

        hosts = [h.strip() for h in _get_test_hosts() if h.strip()]
        if not hosts and not urls:
            logging.warning("offline check failed: no hosts configured")
            return False

        for host in hosts:
            if _try_connect(host, timeout, default_port):
                return True

        logging.warning("offline check failed: all hosts unreachable")
        return False

    except Exception as exc:  # pragma: no cover - unexpected environment failure
        logging.debug("is_system_online error: %s", exc)
        return False
