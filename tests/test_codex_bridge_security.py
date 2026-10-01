import io
from unittest.mock import Mock

import pytest

from scripts import glimpser_codex_web as bridge


def test_file_viewer_confines_paths_and_symlinks(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (workspace / "link").symlink_to(outside)
    monkeypatch.setattr(bridge, "WORKDIR", str(workspace))
    assert bridge.resolve_file_target("camera.txt") == workspace / "camera.txt"
    assert bridge.resolve_file_target("../private.txt") is None
    assert bridge.resolve_file_target(str(outside)) is None
    assert bridge.resolve_file_target("link") is None


def test_file_headers_encode_filename_and_reject_line_breaks(tmp_path):
    path = tmp_path / 'image"\r\nInjected: yes.txt'
    path.write_bytes(b"image")
    handler = object.__new__(bridge.Handler)
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.wfile = io.BytesIO()
    handler.send_file_bytes(
        path, "text/plain\r\nInjected: yes", path.stat(), download=True
    )
    headers = dict(call.args for call in handler.send_header.call_args_list)
    assert headers["Content-Type"] == "application/octet-stream"
    assert headers["Content-Disposition"].startswith("attachment; filename*=UTF-8''")
    assert all("\r" not in value and "\n" not in value for value in headers.values())
    assert handler.wfile.getvalue() == b"image"


def test_remote_bridge_requires_authentication(monkeypatch):
    monkeypatch.setattr(bridge, "HOST", "0.0.0.0")
    monkeypatch.setattr(bridge, "TOKEN", "")
    with pytest.raises(ValueError, match="token is required"):
        bridge.main()
