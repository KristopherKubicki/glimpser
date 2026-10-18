import sys
from pathlib import Path

from app.runtime_paths import application_state_root


def test_source_install_preserves_project_root(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert application_state_root(str(tmp_path / "app/config.py")) == tmp_path


def test_frozen_state_survives_different_extraction_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("GLIMPSER_STATE_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert application_state_root("/bundle-one/app/config.py") == tmp_path / ".glimpser"
    assert application_state_root("/bundle-two/app/config.py") == tmp_path / ".glimpser"


def test_frozen_state_override(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("GLIMPSER_STATE_DIR", str(tmp_path / "state"))
    assert application_state_root("/bundle/app/config.py") == tmp_path / "state"
