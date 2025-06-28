import logging
import time
from typing import Any

import requests


def request_with_retry(
    method: str,
    url: str,
    *,
    retries: int = 2,
    timeout: int = 30,
    backoff_factor: float = 1.0,
    **kwargs: Any,
) -> requests.Response:
    """Send an HTTP request with retries and exponential backoff."""

    attempt = 0
    # Disable proxy use by default to avoid environment interference. Requests
    # will respect proxies passed explicitly via ``kwargs``.
    if "proxies" not in kwargs:
        kwargs["proxies"] = {"http": None, "https": None}

    while True:
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except Exception as exc:
            attempt += 1
            logging.warning("request error: %s", exc)
            if attempt > retries:
                raise
            time.sleep(min(backoff_factor * (2 ** (attempt - 1)), 30))
