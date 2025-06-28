import logging
import os
import socket

import requests


def _get_test_hosts():
    """Return list of hosts to probe for network connectivity."""
    return os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1").split(",")


def is_system_online(timeout: int = 3) -> bool:
    """Return ``True`` if the system can reach any configured test endpoint."""
    default_port = int(os.getenv("ONLINE_TEST_PORT", "443"))
    urls = [
        u.strip()
        for u in os.getenv(
            "ONLINE_TEST_URLS", "https://connectivitycheck.gstatic.com/generate_204"
        ).split(",")
        if u.strip()
    ]

    def parse_target(target: str) -> tuple[str, int]:
        if ":" in target:
            host, p = target.rsplit(":", 1)
            try:
                return host, int(p)
            except ValueError:
                return host, default_port
        return target, default_port

    def check_url(url: str) -> bool:
        try:
            resp = requests.head(url, timeout=timeout)
            return resp.ok
        except Exception as exc:  # pragma: no cover - network depends on environment
            logging.debug("offline check failed for %s: %s", url, exc)
            return False

    def try_connect(target: str) -> bool:
        host, port = parse_target(target)
        try:
            socket.create_connection((host, port), timeout=timeout)
            return True
        except OSError as exc:  # pragma: no cover - network depends on environment
            logging.debug("offline check failed for %s:%s: %s", host, port, exc)
            return False

    # HTTP(S) reachability check similar to Android/iOS captive portal detection
    for url in urls:
        if check_url(url):
            return True

    hosts = [h.strip() for h in _get_test_hosts() if h.strip()]
    if not hosts and not urls:
        logging.warning("offline check failed: no hosts configured")
        return False

    for host in hosts:
        if try_connect(host):
            return True

    logging.warning("offline check failed: all hosts unreachable")
    return False
