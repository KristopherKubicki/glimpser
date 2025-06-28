import logging
import socket
import time
from urllib.parse import urlparse

import requests

from .logging_utils import sanitize_url


def send_http_callback(
    url,
    event_type,
    payload,
    *,
    timeout=5,
    headers=None,
    retries=0,
):
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

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        logging.warning("Invalid callback URL: %s", sanitize_url(url))
        return
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        logging.warning("Callback host does not resolve: %s", host)
        return

    data = {"event": event_type, "payload": payload}
    headers = headers or {}
    attempt = 0
    while True:
        try:
            requests.post(url, json=data, timeout=timeout, headers=headers)
            logging.info("HTTP callback sent to %s", sanitize_url(url))
            break
        except Exception as exc:
            logging.error("HTTP callback error: %s", exc)
            attempt += 1
            if attempt > retries:
                break
            # Exponential backoff capped at 30 seconds prevents a rapid
            # retry loop when the remote service is unavailable.
            time.sleep(min(2**attempt, 30))
