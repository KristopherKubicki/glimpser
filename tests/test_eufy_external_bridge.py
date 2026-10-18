from __future__ import annotations

import sys
from pathlib import Path

from scripts import eufy_external_bridge


def test_normalize_devices_keeps_valid_rows() -> None:
    devices = eufy_external_bridge.normalize_devices(
        [
            {
                "device_id": "cam-1",
                "name": "Driveway",
                "snapshot_path": "/tmp/driveway.png",
            },
            {"name": "missing-id"},
            "bad-row",
        ]
    )

    assert devices == [
        {
            "device_id": "cam-1",
            "name": "Driveway",
            "online": True,
            "snapshot": True,
            "model": "",
            "station": "",
            "snapshot_path": "/tmp/driveway.png",
            "snapshot_cmd": "",
            "content_type": "",
        }
    ]


def test_is_authorized_accepts_bearer_or_x_api_token() -> None:
    class _Headers(dict):
        pass

    bearer = _Headers({"Authorization": "Bearer bridge-secret"})
    alt = _Headers({"X-API-Token": "bridge-secret"})

    assert eufy_external_bridge.is_authorized(bearer, "bridge-secret") is True
    assert eufy_external_bridge.is_authorized(alt, "bridge-secret") is True
    assert eufy_external_bridge.is_authorized(_Headers(), "bridge-secret") is False


def test_snapshot_bytes_for_device_reads_snapshot_path(tmp_path: Path) -> None:
    image_path = tmp_path / "camera.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    payload, content_type = eufy_external_bridge.snapshot_bytes_for_device(
        {
            "device_id": "cam-1",
            "name": "Driveway",
            "snapshot_path": str(image_path),
            "snapshot_cmd": "",
            "content_type": "",
        },
        timeout=2.0,
    )

    assert payload.startswith(b"\x89PNG")
    assert content_type == "image/png"


def test_snapshot_bytes_for_device_runs_snapshot_cmd() -> None:
    payload, content_type = eufy_external_bridge.snapshot_bytes_for_device(
        {
            "device_id": "cam-2",
            "name": "Garage",
            "snapshot_path": "",
            "snapshot_cmd": (
                f"{sys.executable} -c \"import sys; sys.stdout.buffer.write(b'jpeg-data')\""
            ),
            "content_type": "image/jpeg",
        },
        timeout=2.0,
    )

    assert payload == b"jpeg-data"
    assert content_type == "image/jpeg"
