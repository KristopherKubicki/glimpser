import io
import os
import time
from unittest.mock import patch

import pytest
from PIL import Image

from app import routes


@pytest.fixture
def stream_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "SCREENSHOT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(routes, "latest_shot_cache", {})
    monkeypatch.setattr(routes, "last_shot", None)
    monkeypatch.setattr(routes, "last_time", None)
    monkeypatch.setattr(routes, "_overlay_stream_timestamp", lambda frame: frame)
    monkeypatch.setattr(routes.time, "sleep", lambda _: None)
    # Force the shared one-second disk cache to miss, as on each normal tick.
    monkeypatch.setattr(routes.os.path, "getctime", lambda _: 0)
    now = time.time_ns()
    monkeypatch.setattr(routes.time, "time_ns", lambda: now + 10_000_000_000)
    records = {}
    monkeypatch.setattr(routes.template_manager, "get_templates", lambda: records)

    def camera(name, color):
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        path = folder / "latest_camera.png"
        Image.new("RGB", (32, 32), color).save(path)
        records[name] = {"name": name, "groups": "test"}
        return path

    return camera


def frame(generator):
    assert next(generator) == b"--frame\r\n"
    return next(generator).split(b"\r\n\r\n", 1)[1][:-4]


def pixel(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.getpixel((640, 360))


def test_concurrent_camera_streams_never_reuse_other_cameras_shot(stream_setup):
    stream_setup("Red", "red")
    stream_setup("Blue", "blue")
    red = routes.generate(camera="Red")
    blue = routes.generate(camera="Blue")
    try:
        assert pixel(frame(red))[0] > 240
        assert pixel(frame(blue))[2] > 240
        assert pixel(frame(red))[0] > 240
    finally:
        red.close()
        blue.close()


def test_unchanged_source_reuses_encoding_and_replacement_invalidates(stream_setup):
    path = stream_setup("Camera", "red")
    generator = routes.generate(camera="Camera")
    with patch.object(routes, "resize_and_pad", wraps=routes.resize_and_pad) as resize:
        try:
            first = frame(generator)
            assert frame(generator) == first
            assert resize.call_count == 1
            replacement = path.with_suffix(".new.png")
            Image.new("RGB", (32, 32), "blue").save(replacement)
            os.replace(replacement, path)
            assert pixel(frame(generator))[2] > 240
            assert resize.call_count == 2
            path.unlink()
            assert pixel(frame(generator))[2] < 240
        finally:
            generator.close()


def test_symlink_retarget_and_inplace_edit_invalidate(stream_setup):
    path = stream_setup("Camera", "red")
    target = path.with_name("original.png")
    path.rename(target)
    path.symlink_to(target.name)
    generator = routes.generate(camera="Camera")
    try:
        assert pixel(frame(generator))[0] > 240
        Image.new("RGB", (32, 32), "blue").save(target)
        assert pixel(frame(generator))[2] > 240
        replacement = path.with_name("replacement.png")
        Image.new("RGB", (32, 32), "green").save(replacement)
        path.unlink()
        path.symlink_to(replacement.name)
        assert pixel(frame(generator))[1] > 100
    finally:
        generator.close()


def test_recent_files_bypass_cache_and_each_frame_gets_timestamp(
    stream_setup, monkeypatch
):
    stream_setup("Camera", "red")
    monkeypatch.setattr(routes.time, "time_ns", lambda: 0)
    generator = routes.generate(camera="Camera")
    with (
        patch.object(routes, "resize_and_pad", wraps=routes.resize_and_pad) as resize,
        patch.object(
            routes, "_overlay_stream_timestamp", side_effect=lambda data: data
        ) as overlay,
    ):
        try:
            frame(generator)
            frame(generator)
            assert resize.call_count == 2
            assert overlay.call_count == 2
        finally:
            generator.close()


@pytest.mark.parametrize(
    "error",
    [
        PermissionError("denied"),
        OSError("disk full"),
        FileNotFoundError("cache directory unavailable"),
    ],
)
def test_cache_write_failure_preserves_source_and_serves_decoded_frame(
    stream_setup, monkeypatch, error
):
    source = stream_setup("Camera", "red")
    original = source.read_bytes()

    def fail_replace(*args):
        raise error

    monkeypatch.setattr(routes.os, "replace", fail_replace)
    generator = routes.generate(camera="Camera")
    try:
        assert pixel(frame(generator))[0] > 240
        assert source.read_bytes() == original
        assert pixel(frame(generator))[0] > 240
        assert not list(source.parent.parent.glob("*.tmp"))
    finally:
        generator.close()


def test_concurrent_publish_uses_unique_temporary_files(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    target = tmp_path / "stream.jpg"
    images = []
    for color in ("red", "blue"):
        data = io.BytesIO()
        Image.new("RGB", (32, 32), color).save(data, format="JPEG")
        images.append(data.getvalue())
    with patch.object(routes.os, "replace", wraps=routes.os.replace) as replace:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(
                pool.map(
                    lambda i: routes._publish_stream_cache(str(target), images[i % 2]),
                    range(8),
                )
            )
        assert len({call.args[0] for call in replace.call_args_list}) == 8
    assert target.read_bytes() in images
    assert not list(tmp_path.glob("*.tmp"))


def test_cache_creation_failure_preserves_source(stream_setup, monkeypatch):
    source = stream_setup("Camera", "red")
    original = source.read_bytes()

    def denied(*args, **kwargs):
        raise PermissionError("cannot create cache")

    monkeypatch.setattr(routes.tempfile, "NamedTemporaryFile", denied)
    generator = routes.generate(camera="Camera")
    try:
        assert pixel(frame(generator))[0] > 240
        assert source.read_bytes() == original
    finally:
        generator.close()
