"""Frame writes remain atomic and release resources on filesystem errors."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from PIL import Image

from app.utils import event_buffer as eb


@pytest.mark.parametrize("failure", ["encode", "replace", "tempfile"])
def test_failed_write_cleans_partial_and_keeps_previous(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(eb, "EVENT_BUFFER_ROOT", tmp_path)
    directory = tmp_path / "camera" / "frames"
    directory.mkdir(parents=True)
    final = directory / "1000.jpg"
    final.write_bytes(b"previous")
    prepared = Image.new("RGB", (16, 16), "red")
    monkeypatch.setattr(eb, "_prepare_image", lambda *_: prepared)

    def fail_save(image, path, *args, **kwargs):
        Path(path).write_bytes(b"partial")
        raise OSError("disk full")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    if failure == "encode":
        monkeypatch.setattr(Image.Image, "save", fail_save)
    elif failure == "replace":
        monkeypatch.setattr(eb.os, "replace", fail)
    else:
        monkeypatch.setattr(eb.tempfile, "NamedTemporaryFile", fail)
    with pytest.raises(OSError, match="disk full") as retained:
        eb._save_frame("camera", prepared, 1, 640)
    assert retained.traceback
    assert final.read_bytes() == b"previous"
    assert list(directory.iterdir()) == [final]
    with pytest.raises(ValueError, match="closed"):
        prepared.getpixel((0, 0))


def test_overlapping_same_timestamp_writes_use_distinct_temporary_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(eb, "EVENT_BUFFER_ROOT", tmp_path)
    barrier = Barrier(2)
    save = Image.Image.save
    temporary_paths = []

    def synchronized_save(image, path, *args, **kwargs):
        temporary_paths.append(Path(path))
        save(image, path, *args, **kwargs)
        barrier.wait(timeout=5)

    monkeypatch.setattr(Image.Image, "save", synchronized_save)

    def write(color):
        with Image.new("RGB", (16, 16), color) as source:
            result = eb._save_frame("camera", source, 1, 640)
            source.getpixel((0, 0))  # Caller still owns the input image.
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["red", "blue"]))
    assert results[0] == results[1]
    assert len(set(temporary_paths)) == 2
    with Image.open(results[0]) as image:
        image.load()
        assert image.size == (16, 16)
    assert list(results[0].parent.iterdir()) == [results[0]]
