import logging
import time
from typing import Any, Optional

import requests

# Reuse a module-level session for better connection pooling
SESSION = requests.Session()


def request_with_retry(
    method: str,
    url: str,
    *,
    retries: int = 2,
    timeout: int = 30,
    backoff_factor: float = 1.0,
    session: Optional[requests.Session] = None,
    **kwargs: Any,
) -> requests.Response:
    """Send an HTTP request with retries and exponential backoff.

    Args:
        method: HTTP method to use.
        url: Request URL.
        retries: Number of retry attempts.
        timeout: Request timeout in seconds.
        backoff_factor: Factor for exponential backoff between retries.
        session: Optional :class:`requests.Session` to use.

    Returns:
        The ``requests.Response`` object.
    """

    attempt = 0
    sess = session or SESSION
    while True:
        try:
            return sess.request(method, url, timeout=timeout, **kwargs)
        except Exception as exc:
            attempt += 1
            logging.warning("request error: %s", exc)
            if attempt > retries:
                raise
            time.sleep(min(backoff_factor * (2 ** (attempt - 1)), 30))
