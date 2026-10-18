"""Private overrides fail closed and recover without exposing installation data."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module, filename, settings, empty",
    [
        (
            "capture_policy",
            "capture_policy.json",
            {"hubitat_hosts": ["hub.example.test"]},
            {},
        ),
        (
            "viewer_config",
            "viewer_config.json",
            {"presentation": {"Home": "Example"}},
            {},
        ),
        (
            "status_config",
            "status_config.json",
            {"native_event_cameras": {"Example": "camera.example.test"}},
            {},
        ),
    ],
)
def test_default_private_file_override_and_recovery(
    tmp_path, monkeypatch, caplog, module, filename, settings, empty
):
    loader = getattr(importlib.import_module("app." + module), "load_" + module)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    variable = "GLIMPSER_" + module.upper()
    monkeypatch.delenv(variable, raising=False)
    assert loader() == empty
    default = tmp_path / ".config" / "glimpser" / filename
    default.parent.mkdir(parents=True)
    default.write_text(json.dumps(settings))
    loaded = loader()
    for key, value in settings.items():
        assert loaded[key] == value
    # An explicit missing override must not silently use the default install.
    override = tmp_path / "override.json"
    monkeypatch.setenv(variable, str(override))
    assert loader() == empty
    override.write_text('{"private-marker": broken')
    assert loader() == empty
    assert "private-marker" not in caplog.text
    assert str(tmp_path) not in caplog.text
    override.write_text(json.dumps(settings))
    assert loader() == loaded


@pytest.mark.parametrize(
    "module,limit",
    [("capture_policy", 65536), ("viewer_config", 262144), ("location_config", 65536)],
)
def test_oversized_private_file_is_rejected_before_parsing(
    tmp_path, monkeypatch, module, limit
):
    loader = getattr(importlib.import_module("app." + module), "load_" + module)
    path = tmp_path / "large.json"
    path.write_text(" " * limit + "{}")
    monkeypatch.setenv("GLIMPSER_" + module.upper(), str(path))
    assert not loader()
