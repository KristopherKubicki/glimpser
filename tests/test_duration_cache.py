"""Exercise production-extracted teaser functions without app startup side effects."""

import ast
import math
import os
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).parents[1] / "app/utils/video_archiver.py"


@pytest.fixture
def scope():
    tree = ast.parse(SOURCE.read_text())
    nodes = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name in ("_video_identity", "_teaser_video_duration")
    ]
    namespace = dict(
        os=os,
        math=math,
        time=time,
        _TEASER_DURATION_CACHE=OrderedDict(),
        _TEASER_DURATION_LOCK=Lock(),
        _TEASER_DURATION_CACHE_SIZE=512,
        get_video_duration=Mock(return_value=12.0),
    )
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace
    )
    return namespace


def test_unchanged(scope, tmp_path):
    p = tmp_path / "clip"
    p.write_bytes(b"abc")
    for _ in range(10):
        assert scope["_teaser_video_duration"](p) == 12
    assert scope["get_video_duration"].call_count == 1


@pytest.mark.parametrize("change", ["rewrite", "replace", "delete"])
def test_invalidation(scope, tmp_path, change):
    p = tmp_path / "clip"
    p.write_bytes(b"abc")
    scope["_teaser_video_duration"](p)
    stamp = p.stat().st_mtime_ns
    if change == "rewrite":
        time.sleep(0.02)  # Allow the filesystem change-time clock to advance.
        p.write_bytes(b"def")
        os.utime(p, ns=(stamp, stamp))
    elif change == "replace":
        q = tmp_path / "other"
        q.write_bytes(b"abc")
        os.replace(q, p)
    else:
        p.unlink()
    result = scope["_teaser_video_duration"](p)
    assert result == (None if change == "delete" else 12)
    assert scope["get_video_duration"].call_count == (1 if change == "delete" else 2)


@pytest.mark.parametrize("bad", [None, 0, -1, float("nan"), float("inf")])
def test_failures_retry(scope, tmp_path, bad):
    p = tmp_path / "clip"
    p.touch()
    scope["get_video_duration"].side_effect = [bad, 12]
    assert scope["_teaser_video_duration"](p) is None
    assert scope["_teaser_video_duration"](p) == 12
    assert scope["get_video_duration"].call_count == 2


def test_change_during_probe(scope, tmp_path):
    p = tmp_path / "clip"
    p.write_bytes(b"abc")

    def probe(_):
        p.write_bytes(b"changed")
        return 12

    scope["get_video_duration"].side_effect = probe
    assert scope["_teaser_video_duration"](p) is None
    assert not scope["_TEASER_DURATION_CACHE"]


def test_bounded(scope, tmp_path):
    scope["_TEASER_DURATION_CACHE_SIZE"] = 2
    for i in range(3):
        p = tmp_path / str(i)
        p.touch()
        scope["_teaser_video_duration"](p)
    assert len(scope["_TEASER_DURATION_CACHE"]) == 2
    assert str(tmp_path / "0") not in scope["_TEASER_DURATION_CACHE"]


def test_expiry(scope, tmp_path):
    p = tmp_path / "clip"
    p.touch()
    scope["_teaser_video_duration"](p)
    identity, duration, _ = scope["_TEASER_DURATION_CACHE"][str(p)]
    scope["_TEASER_DURATION_CACHE"][str(p)] = (
        identity,
        duration,
        time.monotonic() - 3601,
    )
    scope["_teaser_video_duration"](p)
    assert scope["get_video_duration"].call_count == 2
