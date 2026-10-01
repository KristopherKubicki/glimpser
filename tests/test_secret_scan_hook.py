"""A missing or failing secret scanner must never pass the release gate."""

import importlib.util
import runpy
import subprocess
from pathlib import Path
from unittest.mock import Mock


def test_missing_scanner_fails(monkeypatch, capsys):
    hook = runpy.run_path(str(Path("detect-secrets-hook")))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert hook["main"](["app/config.py"]) == 1
    assert "required" in capsys.readouterr().err


def test_scanner_receives_files_and_failure_propagates(monkeypatch):
    hook = runpy.run_path(str(Path("detect-secrets-hook")))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    call = Mock(return_value=1)
    monkeypatch.setattr(subprocess, "call", call)
    assert hook["main"](["app/config.py"]) == 1
    assert call.call_args.args[0][-1] == "app/config.py"
