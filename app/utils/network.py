import logging
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil


def _has_active_lan() -> bool:
    """Return ``True`` if any non-loopback interface is up with a valid IPv4 address."""

    stats = psutil.net_if_stats()
    for iface, addrs in psutil.net_if_addrs().items():
        if iface == "lo" or not stats.get(iface) or not stats[iface].isup:
            continue
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            ip = addr.address
            if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                continue
            return True
    return False


def _get_test_hosts():
    """Return list of hosts to probe for network connectivity."""
    return os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1").split(",")


def is_system_online(timeout: int = 3) -> bool:
    """Return ``True`` if a network connection can be opened to any test host."""
    port = int(os.getenv("ONLINE_TEST_PORT", "443"))

    def try_connect(host: str) -> bool:
        try:
            socket.create_connection((host, port), timeout=timeout)
            return True
        except OSError as exc:  # pragma: no cover - network depends on environment
            logging.debug("offline check failed for %s: %s", host, exc)
            return False

    hosts = [h.strip() for h in _get_test_hosts() if h.strip()]
    if not hosts:
        logging.warning("offline check failed: no hosts configured")
        return False

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(try_connect, host): host for host in hosts}
        for future in as_completed(futures):
            if future.result():
                return True

    if _has_active_lan():
        logging.info("offline check fallback: LAN interface active")
        return True

    logging.warning("offline check failed: all hosts unreachable")
    return False
