import socket
import logging


def is_system_online(timeout: int = 3) -> bool:
    """Return ``True`` if an external network connection can be opened."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError as exc:  # pragma: no cover - network depends on environment
        logging.warning("offline check failed: %s", exc)
        return False
