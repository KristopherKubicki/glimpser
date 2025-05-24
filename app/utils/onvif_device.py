"""Minimal ONVIF device implementation.

This module exposes a very small subset of the ONVIF specification so that
integration tests can discover a local device and receive motion events.  The
implementation is intentionally lightweight and only supports the features that
the application requires:

* Respond to WS-Discovery probe messages on UDP port 3702.
* Provide a tiny HTTP service exposing ``GetCapabilities`` and a basic event
  subscription endpoint.
* Allow the scheduler to notify subscribers when motion is detected.
"""

from __future__ import annotations

import logging
import socket
import threading
import struct
from typing import List, Set

import requests
from flask import Flask, request, Response
from werkzeug.serving import make_server


MCAST_ADDR = "239.255.255.250"
MCAST_PORT = 3702


class _HTTPServerThread(threading.Thread):
    """Thread wrapper for the Flask HTTP server."""

    def __init__(self, app: Flask, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self._server = make_server(host, port, app)

    def run(self) -> None:  # pragma: no cover - trivial wrapper
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()


class ONVIFDevice:
    """Very small ONVIF device used for tests and simple integrations."""

    def __init__(self, host: str = "0.0.0.0", http_port: int = 50080) -> None:
        self.host = host
        self.http_port = http_port
        self.subscribers: Set[str] = set()
        self._udp_sock: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._http_thread: _HTTPServerThread | None = None
        self.running = False

        # Build the Flask application
        app = Flask(__name__)

        @app.route("/onvif/device_service", methods=["POST"])
        def device_service() -> Response:
            xml = request.data.decode("utf-8")
            if "GetCapabilities" in xml:
                body = (
                    "<td:GetCapabilitiesResponse xmlns:td='http://www.onvif.org/ver10/device/wsdl'>"
                    f"<td:Capabilities><tt:Events><tt:XAddr>http://{self.host}:{self.http_port}/onvif/event_service"  # noqa: E501
                    "</tt:XAddr></tt:Events></td:Capabilities></td:GetCapabilitiesResponse>"
                )
                envelope = (
                    "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope' "
                    "xmlns:tt='http://www.onvif.org/ver10/schema'>"
                    f"<s:Body>{body}</s:Body></s:Envelope>"
                )
                return Response(envelope, content_type="application/soap+xml")

            if "Subscribe" in xml or "CreatePullPointSubscription" in xml:
                try:
                    start = xml.index("<Address>") + len("<Address>")
                    end = xml.index("</Address>")
                    addr = xml[start:end]
                    self.subscribers.add(addr)
                except Exception:
                    pass
                resp = (
                    "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'>"
                    "<s:Body/></s:Envelope>"
                )
                return Response(resp, content_type="application/soap+xml")

            return Response("", content_type="application/soap+xml")

        # Event service placeholder (mostly needed for capability checks)
        @app.route("/onvif/event_service", methods=["POST"])
        def event_service() -> Response:  # pragma: no cover - simple echo
            return Response("", content_type="application/soap+xml")

        self.app = app

    # ------------------------------------------------------------------
    # Public control methods
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the UDP and HTTP servers in background threads."""

        if self.running:
            return
        self.running = True

        # UDP listener thread
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._udp_sock.bind((self.host, MCAST_PORT))
        except Exception as exc:  # pragma: no cover - unlikely
            logging.error("Unable to bind ONVIF UDP socket: %s", exc)
            return

        def udp_loop() -> None:
            sock = self._udp_sock
            if not sock:
                return
            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                except Exception:
                    break
                if b"Probe" in data:
                    resp = (
                        "<e:Envelope xmlns:e='http://www.w3.org/2003/05/soap-envelope' "
                        "xmlns:a='http://schemas.xmlsoap.org/ws/2004/08/addressing' "
                        "xmlns:d='http://schemas.xmlsoap.org/ws/2005/04/discovery'>"
                        "<e:Body><d:ProbeMatches><d:ProbeMatch>"
                        f"<d:XAddrs>http://{self.host}:{self.http_port}/onvif/device_service</d:XAddrs>"
                        "</d:ProbeMatch></d:ProbeMatches></e:Body></e:Envelope>"
                    )
                    try:
                        sock.sendto(resp.encode(), addr)
                    except Exception as exc:
                        logging.debug("ONVIF probe response failed: %s", exc)

        self._udp_thread = threading.Thread(target=udp_loop, daemon=True)
        self._udp_thread.start()

        # HTTP server thread
        self._http_thread = _HTTPServerThread(self.app, self.host, self.http_port)
        self._http_thread.start()

    def stop(self) -> None:
        """Stop background threads and close sockets."""

        self.running = False
        if self._http_thread:
            self._http_thread.shutdown()
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except Exception:
                pass

    def send_motion_event(self) -> None:
        """Notify all subscribed clients of a motion event."""

        body = (
            "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'>"
            "<s:Body><MotionEvent>true</MotionEvent></s:Body></s:Envelope>"
        )
        for url in list(self.subscribers):
            try:
                requests.post(url, data=body, timeout=5)
            except Exception as exc:
                logging.debug("ONVIF event delivery error: %s", exc)


_device: ONVIFDevice | None = None


def start_server(host: str, port: int) -> None:
    """Create and start the global ONVIF device."""

    global _device
    if _device is None:
        _device = ONVIFDevice(host=host, http_port=port)
        _device.start()


def send_motion_event() -> None:
    """Helper used by the scheduler to broadcast motion events."""

    if _device is not None:
        _device.send_motion_event()

