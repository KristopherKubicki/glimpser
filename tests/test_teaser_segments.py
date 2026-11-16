"""Regression coverage for bounded, flushed teaser concat manifests."""

import ast
import glob
import logging
import os
import tempfile
import time
from pathlib import Path

import pytest


@pytest.mark.parametrize("duration", [3.0, 120.0])
def test_teasers_use_same_recent_segment_and_flush(tmp_path, duration):
    """Every group must use the same bounded segment as the combined teaser."""
    source = Path(__file__).parents[1] / "app/utils/video_archiver.py"
    tree = ast.parse(source.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "compile_to_teaser"
    )
    camera = tmp_path / "camera"
    camera.mkdir()
    recording = camera / "in_process.mp4"
    recording.write_bytes(b"full recording remains unchanged")
    before = recording.read_bytes()
    manifests = {}

    def compile_video(input_path, output_path):
        # Opening independently reproduces FFmpeg seeing only flushed contents.
        manifests[Path(output_path).name] = Path(input_path).read_text()

    namespace = {
        "_measure_archive_job": lambda function: function,
        "os": os,
        "glob": glob,
        "logging": logging,
        "tempfile": tempfile,
        "time": time,
        "VIDEO_DIRECTORY": str(tmp_path),
        "get_templates": lambda: {"camera": {"groups": "one, two"}},
        "_teaser_video_duration": lambda _: duration,
        "compile_videos": compile_video,
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    namespace["compile_to_teaser"]()
    assert set(manifests) == {
        "all_in_process.mp4",
        "one_in_process.mp4",
        "two_in_process.mp4",
    }
    expected = (
        f"file '{recording}'\ninpoint {max(duration - 5, 0)}\noutpoint {duration}\n"
    )
    assert all(manifest == expected for manifest in manifests.values())
    assert recording.read_bytes() == before
