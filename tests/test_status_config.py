"""Private status inventory never enables probes from missing or invalid input."""

import json

import pytest

from app.status_config import load_status_config


def test_unconfigured(monkeypatch):
    monkeypatch.delenv("GLIMPSER_STATUS_CONFIG", raising=False)
    assert load_status_config() == {}


def test_private_inventory(tmp_path, monkeypatch):
    path = tmp_path / "inventory.json"
    monkeypatch.setenv("GLIMPSER_STATUS_CONFIG", str(path))
    path.write_text(
        json.dumps(
            {
                "hub": "http://hub.example.test",
                "sensors": [["1", "Door", "contact"]],
                "nodes": [
                    [
                        "gpu",
                        "Compute",
                        "Compute",
                        "gpu.example.test",
                        None,
                        "Isolated inference",
                        "",
                        "Isolated",
                    ]
                ],
            }
        )
    )
    config = load_status_config()
    assert config["nodes"][0][4] is None
    assert config["sensors"] == [("1", "Door", "contact")]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"sensors": [["../secret", "Door", "contact"]]},
        {
            "hub": "http://user:pass@hub.example.test",  # pragma: allowlist secret -- synthetic rejection fixture
            "sensors": [["1", "Door", "contact"]],
        },
        {"nodes": [["a", "A", "Home", "host.test", True, "Service", "", "TCP"]]},
        {
            "nodes": [
                [
                    "a",
                    "A",
                    "Home",
                    "host.test",
                    443,
                    "Service",
                    "javascript:alert(1)",
                    "TCP",
                ]
            ]
        },
    ],
)
def test_invalid_inventory_disables_all_probes(tmp_path, monkeypatch, data):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data))
    monkeypatch.setenv("GLIMPSER_STATUS_CONFIG", str(path))
    assert load_status_config() == {}
