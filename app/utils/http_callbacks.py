import logging
import requests


def send_http_callback(url, event_type, payload):
    """Send an HTTP POST callback if a URL is provided."""
    if not url:
        return
    try:
        data = {"event": event_type, "payload": payload}
        requests.post(url, json=data, timeout=5)
        logging.info("HTTP callback sent to %s", url)
    except Exception as e:
        logging.error("HTTP callback error: %s", e)

