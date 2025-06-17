import logging
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed


def _get_test_hosts():
    """Return list of hosts to probe for network connectivity."""
    return os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1").split(",")


def is_system_online(timeout: int = 3) -> bool:
    """Return ``True`` if a network connection can be opened to any test host."""
    default_port = int(os.getenv("ONLINE_TEST_PORT", "443"))

    def parse_target(target: str) -> tuple[str, int]:
        if ":" in target:
            host, p = target.rsplit(":", 1)
            try:
                return host, int(p)
            except ValueError:
                return host, default_port
        return target, default_port

    def try_connect(target: str) -> bool:
        host, port = parse_target(target)
        try:
            socket.create_connection((host, port), timeout=timeout)
            return True
        except OSError as exc:  # pragma: no cover - network depends on environment
            logging.debug("offline check failed for %s:%s: %s", host, port, exc)
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

    logging.warning("offline check failed: all hosts unreachable")
    return False
