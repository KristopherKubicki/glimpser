"""Avoid repeat encoding without serving an older capture or unbounded data."""

import os
from collections import OrderedDict
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from app.blueprints import assets


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch):
    monkeypatch.setattr(assets, "_fitted_cache", OrderedDict())
    monkeypatch.setattr(assets, "_fitted_cache_bytes", 0)


def fitted(path, **args):
    routes = SimpleNamespace(
        request=SimpleNamespace(args={"fit": "contain", "w": "80", "h": "60", **args}),
        PNG_TTL_SEC=3,
        send_conditional_file=lambda file, **kwargs: file.read(),
    )
    return assets._serve_fitted_screenshot(routes, str(path))


def test_repeated_frame_is_encoded_once_and_replacement_invalidates(tmp_path):
    frame = tmp_path / "capture.png"
    Image.new("RGB", (80, 60), "red").save(frame)
    stamp = frame.stat()
    original = Image.Image.save
    with patch.object(
        Image.Image, "save", autospec=True, side_effect=original
    ) as encode:
        first = fitted(frame)
        assert fitted(frame) == first
        assert encode.call_count == 1
    replacement = tmp_path / "replacement.png"
    Image.new("RGB", (80, 60), "blue").save(replacement)
    os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    replacement.replace(frame)
    second = fitted(frame)
    assert second != first
    with Image.open(BytesIO(second)) as image:
        assert image.getpixel((40, 30)) == (0, 0, 255)


def test_symlink_retarget_and_variant_options_do_not_reuse_wrong_image(tmp_path):
    one, two, link = (tmp_path / name for name in ("one.png", "two.png", "latest.png"))
    Image.new("RGB", (20, 40), "red").save(one)
    Image.new("RGB", (20, 40), "blue").save(two)
    link.symlink_to(one)
    first = fitted(link)
    with Image.open(BytesIO(fitted(link, bg="ffffff", w="100"))) as image:
        assert image.size == (100, 60)
        assert image.getpixel((0, 0)) == (255, 255, 255)
    link.unlink()
    link.symlink_to(two)
    assert fitted(link) != first


def test_changed_during_encode_is_not_cached(tmp_path, monkeypatch):
    frame = tmp_path / "capture.png"
    Image.new("RGB", (40, 40), "red").save(frame)
    versions = iter([("before",), ("after",)])
    monkeypatch.setattr(assets, "_fitted_source_version", lambda path: next(versions))
    assert fitted(frame)
    assert not assets._fitted_cache


def test_deleted_source_never_returns_cached_frame(tmp_path):
    frame = tmp_path / "capture.png"
    Image.new("RGB", (40, 40), "red").save(frame)
    assert fitted(frame)
    frame.unlink()
    assert fitted(frame) is None


def test_cache_bytes_and_entries_are_bounded(monkeypatch):
    monkeypatch.setattr(assets, "_FITTED_CACHE_MAX_BYTES", 10)
    monkeypatch.setattr(assets, "_FITTED_CACHE_MAX_ENTRIES", 2)
    assets._remember_fitted((1,), b"123456")
    assets._remember_fitted((2,), b"123456")
    assert list(assets._fitted_cache) == [(2,)]
    assets._remember_fitted((2,), b"12")
    assets._remember_fitted((3,), b"12")
    assets._remember_fitted((4,), b"12")
    assets._remember_fitted((5,), b"01234567890")
    assert list(assets._fitted_cache) == [(3,), (4,)]
    assert assets._fitted_cache_bytes == 4
