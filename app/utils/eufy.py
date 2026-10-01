"""Eufy integration helpers.

Glimpser supports Eufy cameras primarily via standard camera protocols
(RTSP and/or ONVIF) when enabled on the device.

This module does *not* attempt to reverse engineer Eufy's cloud APIs.
Those APIs are unofficial and change frequently. Instead we provide:

- Vendor detection helpers (Anker / Eufy).
- Best-effort RTSP path suggestions for common Eufy devices that expose RTSP.

Glimpser now also includes a first-class Eufy cloud bridge integration in
``app.utils.eufy_cloud``. This module remains focused on local RTSP/ONVIF paths.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RtspCandidate:
    url: str
    note: str


_EUFY_VENDOR_TOKENS = (
    "eufy",
    "anker",
    "anker innovations",
)


def is_eufy_vendor(vendor: str | None) -> bool:
    if not vendor:
        return False
    v = vendor.strip().lower()
    return any(tok in v for tok in _EUFY_VENDOR_TOKENS)


def suggest_rtsp_urls(
    ip: str,
    *,
    port: int = 554,
    username: str | None = None,
    password: str | None = None,
) -> list[RtspCandidate]:
    """Return common RTSP URL candidates for Eufy devices.

    Many Eufy cameras expose RTSP only after explicitly enabling it in the Eufy
    Security app. The exact RTSP path can vary by model/firmware.

    The candidates here are intentionally conservative and ordered by likelihood.
    """

    auth = ""
    if username is not None:
        if password is None:
            password = ""
        auth = f"{username}:{password}@"

    host = f"{auth}{ip}:{int(port)}"

    paths: list[tuple[str, str]] = [
        ("/live0", "Eufy IndoorCam/solo cams commonly use /live0"),
        ("/live1", "Some devices expose a secondary stream as /live1"),
        ("/live2", "Some devices expose a tertiary stream as /live2"),
        (
            "/Streaming/Channels/101",
            "Hikvision-style main stream (seen on some OEM firmwares)",
        ),
        ("/Streaming/Channels/102", "Hikvision-style sub stream"),
    ]

    return [
        RtspCandidate(url=f"rtsp://{host}{path}", note=note) for path, note in paths
    ]
