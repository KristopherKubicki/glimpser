"""Small external HTTP bridge for Mac-hosted Eufy snapshot services.

The bridge intentionally exposes only two Glimpser-facing surfaces:

- ``GET /api/devices``
- ``GET /api/cameras/<device_id>/snapshot``

It does not try to automate the Eufy app itself. Instead, it lets a host-local
capture workflow provide either:

- a stable ``snapshot_path`` per device, or
- a bounded ``snapshot_cmd`` per device

This keeps the Glimpser connector narrow and avoids using noVNC/VNC as the
primary integration surface.
"""

from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import shlex
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def load_bridge_config(path: str | Path) -> dict[str, Any]:
    """Load JSON bridge config from disk."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Bridge config must be a JSON object.")
    return payload


def normalize_devices(payload: object) -> list[dict[str, Any]]:
    """Return sanitized device entries from bridge config."""

    if not isinstance(payload, list):
        return []

    devices: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        device_id = str(item.get("device_id") or "").strip()
        if not device_id:
            continue
        name = str(item.get("name") or device_id).strip() or device_id
        devices.append(
            {
                "device_id": device_id,
                "name": name,
                "online": bool(item.get("online", True)),
                "snapshot": bool(item.get("snapshot", True)),
                "model": str(item.get("model") or "").strip(),
                "station": str(item.get("station") or "").strip(),
                "snapshot_path": str(item.get("snapshot_path") or "").strip(),
                "snapshot_cmd": str(item.get("snapshot_cmd") or "").strip(),
                "content_type": str(item.get("content_type") or "").strip(),
            }
        )
    return devices


def visible_device_payload(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only the Glimpser-facing device metadata."""

    out: list[dict[str, Any]] = []
    for item in devices:
        out.append(
            {
                "device_id": item["device_id"],
                "name": item["name"],
                "online": bool(item.get("online", True)),
                "snapshot": bool(item.get("snapshot", True)),
                "model": str(item.get("model") or "").strip(),
                "station": str(item.get("station") or "").strip(),
            }
        )
    return out


def bridge_token(payload: dict[str, Any]) -> str:
    """Return configured bridge token or empty string."""

    return str(payload.get("api_token") or "").strip()


def is_authorized(headers: Any, expected_token: str) -> bool:
    """Return whether request headers satisfy bridge auth."""

    expected = str(expected_token or "").strip()
    if not expected:
        return True

    auth = str(getattr(headers, "get", lambda *_a, **_k: "")("Authorization") or "")
    if auth.startswith("Bearer "):
        candidate = auth[7:].strip()
        if candidate and hmac.compare_digest(candidate, expected):
            return True

    alt = str(getattr(headers, "get", lambda *_a, **_k: "")("X-API-Token") or "")
    return bool(alt and hmac.compare_digest(alt.strip(), expected))


def get_device(payload: dict[str, Any], device_id: str) -> dict[str, Any] | None:
    """Return the configured device entry by id."""

    wanted = str(device_id or "").strip()
    for item in normalize_devices(payload.get("devices")):
        if item["device_id"] == wanted:
            return item
    return None


def _guess_content_type(device: dict[str, Any]) -> str:
    explicit = str(device.get("content_type") or "").strip()
    if explicit:
        return explicit

    snapshot_path = str(device.get("snapshot_path") or "").strip()
    guessed, _ = mimetypes.guess_type(snapshot_path)
    if guessed:
        return guessed
    return "image/png"


def _render_command_template(command: str, device: dict[str, Any]) -> list[str]:
    rendered = (
        str(command or "")
        .replace("{device_id}", str(device.get("device_id") or ""))
        .replace("{name}", str(device.get("name") or ""))
    )
    args = shlex.split(rendered)
    if not args:
        raise ValueError("Snapshot command is empty.")
    return args


def snapshot_bytes_for_device(
    device: dict[str, Any], *, timeout: float
) -> tuple[bytes, str]:
    """Return image bytes for one configured device."""

    snapshot_path = str(device.get("snapshot_path") or "").strip()
    if snapshot_path:
        data = Path(snapshot_path).read_bytes()
        return data, _guess_content_type(device)

    snapshot_cmd = str(device.get("snapshot_cmd") or "").strip()
    if snapshot_cmd:
        args = _render_command_template(snapshot_cmd, device)
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1.0, float(timeout)),
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(
                stderr or f"Snapshot command failed: {result.returncode}"
            )
        return result.stdout, _guess_content_type(device)

    raise FileNotFoundError("Device is missing snapshot_path and snapshot_cmd.")


def make_handler(config: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    """Return a request handler bound to a specific bridge config."""

    class EufyExternalBridgeHandler(BaseHTTPRequestHandler):
        server_version = "GlimpserEufyBridge/1.0"

        def log_message(self, format: str, *args: object) -> None:
            """Keep logging simple and stdout-friendly."""

            print(
                "%s - - [%s] %s"
                % (
                    self.client_address[0],
                    self.log_date_time_string(),
                    format % args,
                )
            )

        def _send_json(self, payload: object, *, status: int = 200) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_image(self, payload: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _unauthorized(self) -> None:
            self._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)

        def do_GET(self) -> None:  # noqa: N802
            """Serve bridge endpoints."""

            if not is_authorized(self.headers, bridge_token(config)):
                self._unauthorized()
                return

            if self.path == "/health":
                self._send_json(
                    {
                        "ok": True,
                        "devices": len(normalize_devices(config.get("devices"))),
                    }
                )
                return

            if self.path == "/api/devices":
                self._send_json(
                    {
                        "devices": visible_device_payload(
                            normalize_devices(config.get("devices"))
                        )
                    }
                )
                return

            prefix = "/api/cameras/"
            suffix = "/snapshot"
            if self.path.startswith(prefix) and self.path.endswith(suffix):
                device_id = self.path[len(prefix) : -len(suffix)].strip("/")
                device = get_device(config, device_id)
                if not device:
                    self._send_json(
                        {"error": "unknown_device"}, status=HTTPStatus.NOT_FOUND
                    )
                    return
                timeout = float(config.get("snapshot_timeout_seconds") or 10.0)
                try:
                    payload, content_type = snapshot_bytes_for_device(
                        device, timeout=timeout
                    )
                except Exception as exc:
                    self._send_json(
                        {
                            "error": "snapshot_failed",
                            "message": str(exc),
                            "device_id": device_id,
                        },
                        status=HTTPStatus.BAD_GATEWAY,
                    )
                    return
                self._send_image(payload, content_type)
                return

            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    return EufyExternalBridgeHandler


def run_server(config: dict[str, Any]) -> None:
    """Start the bridge HTTP server."""

    host = str(config.get("listen_host") or "0.0.0.0").strip() or "0.0.0.0"
    port = int(config.get("listen_port") or 8084)
    server = ThreadingHTTPServer((host, port), make_handler(config))
    print(f"Listening on http://{host}:{port}")
    server.serve_forever()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to bridge JSON config.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)
    config = load_bridge_config(args.config)
    run_server(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
