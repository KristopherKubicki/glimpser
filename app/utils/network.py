import socket
import logging
import os


def _get_test_hosts():
    """Return list of hosts to probe for network connectivity."""
    return os.getenv("ONLINE_TEST_HOSTS", "8.8.8.8,1.1.1.1").split(",")


def is_system_online(timeout: int = 3) -> bool:
    """Return ``True`` if a network connection can be opened to any test host.

    When the ``NO_NETWORK`` environment variable is set to ``"1"`` the
    function immediately returns ``False`` without attempting any socket
    connections. This speeds up tests in offline environments by avoiding
    lengthy connection timeouts.
    """

    if os.getenv("NO_NETWORK") == "1":
        logging.info("offline mode enabled via NO_NETWORK")
        return False
    for host in _get_test_hosts():
        host = host.strip()
        if not host:
            continue
        try:
            socket.create_connection((host, 53), timeout=timeout)
            return True
        except OSError as exc:  # pragma: no cover - network depends on environment
            logging.debug("offline check failed for %s: %s", host, exc)

    logging.warning("offline check failed: all hosts unreachable")
    return False
