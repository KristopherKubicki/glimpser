import logging
import time
from typing import Any, Dict, Optional

import requests


def send_http_callback(
    url: str,
    event_type: str,
    payload: Dict[str, Any],
    *,
    timeout: int = 5,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 0,
) -> None:
    """Send an HTTP POST callback if a URL is provided.

    Parameters
    ----------
    url : str
        Destination URL for the callback.
    event_type : str
        Type of event being reported.
    payload : dict
        Data payload to include in the POST body.
    timeout : int, optional
        Request timeout in seconds. Defaults to ``5``.
    headers : dict, optional
        Additional HTTP headers to include.
    retries : int, optional
        Number of retry attempts on failure.

    Failures are logged. Retries use exponential backoff to avoid
    hammering the remote service.
    """
    if not url:
        return

    data = {"event": event_type, "payload": payload}
    headers = headers or {}
    attempt = 0
    while True:
        try:
            requests.post(url, json=data, timeout=timeout, headers=headers)
            logging.info("HTTP callback sent to %s", url)
            break
        except Exception as exc:
            logging.error("HTTP callback error: %s", exc)
            attempt += 1
            if attempt > retries:
                break
            # Exponential backoff capped at 30 seconds prevents a rapid
            # retry loop when the remote service is unavailable.
            time.sleep(min(2**attempt, 30))
