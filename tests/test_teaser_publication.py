"""Teaser failures must never remove or expose a partial published video."""

import ast
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


@pytest.mark.parametrize("outcome", ["success", "timeout", "small", "publish_error"])
def test_teaser_publication(tmp_path, outcome, caplog, monkeypatch):
    source = Path(__file__).parents[1] / "app/utils/video_archiver.py"
    function = next(
        node
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "compile_videos"
    )
    output = tmp_path / "published.mp4"
    previous = b"previous complete video"
    replacement = b"new complete video" * 100
    output.write_bytes(previous)
    manifest = tmp_path / "frames.txt"
    manifest.write_text("file 'source.mp4'\n")
    staged = []

    def encode(command, timeout):
        assert timeout == 30
        assert output.read_bytes() == previous
        pending = Path(command[-1])
        assert pending.parent == output.parent
        assert pending != output
        staged.append(pending)
        pending.write_bytes(replacement if outcome != "small" else b"x")
        assert output.read_bytes() == previous
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(
                command, 30, stderr=b"moving the moov atom private-source"
            )

    if outcome == "publish_error":

        def fail_replace(*_):
            raise OSError("publication failed")

        monkeypatch.setattr(os, "replace", fail_replace)

    namespace = {
        "os": os,
        "tempfile": tempfile,
        "time": time,
        "subprocess": subprocess,
        "logging": logging,
        "FFMPEG_PATH": "ffmpeg",
        "FFMPEG_HWACCEL": False,
        "MIN_VALID_MP4_BYTES": 100,
        "MAX_COMPRESSED_VIDEO_AGE": 30,
        "_concat_list_has_entries": lambda _: True,
        "run_ffmpeg": encode,
        "is_video_expired": lambda *_: False,
        "_log_ffmpeg_failure": lambda *_: None,
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    assert namespace["compile_videos"](str(manifest), str(output)) == (
        outcome == "success"
    )
    assert output.read_bytes() == (replacement if outcome == "success" else previous)
    assert staged and all(not path.exists() for path in staged)
    if outcome == "timeout":
        assert "timeout=True faststart_started=True" in caplog.text
        assert "private-source" not in caplog.text
