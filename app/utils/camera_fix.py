import logging
from typing import Any

import requests

from . import camera_discovery

try:  # optional lxml
    from lxml import html as lxml_html  # type: ignore
except Exception:  # pragma: no cover - optional dependency may be missing
    lxml_html = None
from xml.etree import ElementTree


def _check_xpath(content: bytes, xpath: str) -> bool:
    """Return ``True`` if ``xpath`` matches an element in ``content``."""
    if not xpath:
        return False
    if lxml_html is not None:
        try:
            tree = lxml_html.fromstring(content)
            return bool(tree.xpath(xpath))
        except Exception as exc:  # pragma: no cover - runtime only
            logging.debug("lxml xpath error: %s", exc)
            return False
    try:
        tree = ElementTree.fromstring(content)
        return bool(tree.findall(xpath))
    except Exception as exc:  # pragma: no cover - runtime only
        logging.debug("ElementTree xpath error: %s", exc)
        return False


def check_camera_template(
    url: str, xpaths: list[str], timeout: int = 5
) -> dict[str, Any]:
    """Validate ``url`` and ``xpaths``.

    Parameters
    ----------
    url : str
        Page or stream URL to check.
    xpaths : list[str]
        Any XPaths expected to be present in the returned document.
    timeout : int
        HTTP request timeout in seconds.

    Returns
    -------
    dict
        Diagnostic information and potential replacement URLs.
    """

    result: dict[str, Any] = {
        "valid_url": False,
        "url_error": "",
        "xpath_results": {},
        "suggestions": [],
    }

    try:
        resp = requests.get(url, timeout=timeout)
        result["valid_url"] = resp.ok
        if resp.ok:
            for xp in xpaths:
                result["xpath_results"][xp] = _check_xpath(resp.content, xp)
        else:
            result["url_error"] = f"status {resp.status_code}"
    except Exception as exc:
        result["url_error"] = str(exc)

    if not result["valid_url"]:
        try:
            cams = camera_discovery.discover_cameras()
        except Exception as exc:  # pragma: no cover - network
            logging.error("discovery error: %s", exc)
            cams = []
        suggestions = []
        for cam in cams:
            if "url" in cam:
                suggestions.append(cam["url"])
                continue
            ip = cam.get("ip")
            proto = cam.get("protocol")
            port = cam.get("port")
            path = cam.get("info", {}).get("path", "")
            if proto == "http" or proto == "hls":
                suggestions.append(f"http://{ip}:{port}{path}")
            elif proto == "rtsp":
                suggestions.append(f"rtsp://{ip}:{port}{path}")
            elif proto == "rtmp":
                suggestions.append(f"rtmp://{ip}:{port}/")
            elif proto == "local":
                suggestions.append(str(ip))
        result["suggestions"] = list(dict.fromkeys(suggestions))
    return result
