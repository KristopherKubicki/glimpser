"""Archive scans must reuse unchanged checks without trusting changed files."""

import os
import time
from unittest.mock import Mock

import pytest
from PIL import Image

from app.utils import video_archiver as archive
from app.utils.screenshots import _is_valid_png


@pytest.fixture(autouse=True)
def clear_validation_cache():
    archive._cached_archive_check.cache_clear()
    yield
    archive._cached_archive_check.cache_clear()


def test_limit_matches_existing_newest_nonblank_selection(tmp_path, monkeypatch):
    for index in range(10):
        color = "black" if index in (7, 9) else "red"
        Image.new("RGB", (32, 32), color).save(
            tmp_path / f"cam_202609280000{index:02d}.png"
        )
    monkeypatch.setattr(
        archive, "is_mostly_blank", lambda image: image.getpixel((0, 0)) == (0, 0, 0)
    )
    check = Mock(wraps=archive._frame_has_content)
    monkeypatch.setattr(archive, "_frame_has_content", check)
    limited = archive._collect_new_frame_files(str(tmp_path), "cam", 0, limit=3)
    assert check.call_count == 5  # newest three useful frames, plus two blanks
    full = archive._collect_new_frame_files(str(tmp_path), "cam", 0)
    assert limited == full[-3:]
    assert archive._collect_new_frame_files(str(tmp_path), "cam", 0, limit=0) == []


def test_unchanged_validity_is_reused_but_inplace_corruption_is_rejected(tmp_path):
    path = tmp_path / "frame.png"
    Image.new("RGB", (32, 32), "red").save(path)
    original = path.read_bytes()
    stamp = path.stat()
    time.sleep(1.05)  # Stable frames are cached; freshly written frames are not.
    check = Mock(wraps=_is_valid_png)
    assert archive._archive_check(str(path), check)
    assert archive._archive_check(str(path), check)
    assert check.call_count == 1
    path.write_bytes(b"x" * len(original))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert path.stat().st_ino == stamp.st_ino
    assert not archive._archive_check(str(path), check)
    assert check.call_count == 2
    path.write_bytes(original)
    assert archive._archive_check(str(path), check)
    assert check.call_count == 3


def test_atomic_replacement_and_deletion_invalidate(tmp_path):
    path, replacement = tmp_path / "frame.png", tmp_path / "new.png"
    Image.new("RGB", (32, 32), "red").save(path)
    check = Mock(wraps=_is_valid_png)
    assert archive._archive_check(str(path), check)
    replacement.write_bytes(b"broken")
    replacement.replace(path)
    assert not archive._archive_check(str(path), check)
    path.unlink()
    assert not archive._archive_check(str(path), check)


def test_changed_during_check_is_not_accepted(tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"original")

    def changed(filename):
        path.write_bytes(b"changed while checking")
        return True

    assert not archive._archive_check(str(path), changed)


def test_recent_frame_checks_are_not_cached(tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"new frame")
    check = Mock(return_value=True)
    assert archive._archive_check(str(path), check)
    assert archive._archive_check(str(path), check)
    assert check.call_count == 2
    assert archive._cached_archive_check.cache_info().currsize == 0


def test_truncated_frame_still_fails_with_pillow_tolerance(tmp_path, monkeypatch):
    from PIL import ImageFile

    path = tmp_path / "frame.png"
    Image.new("RGB", (32, 32), "red").save(path)
    path.write_bytes(path.read_bytes()[:-20])
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", True)
    assert not archive._archive_check(str(path), _is_valid_png)


@pytest.mark.parametrize("scene", ["white", "black", "night", "pattern"])
@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P"])
def test_combined_check_matches_original_guards(tmp_path, scene, mode):
    image = Image.new("RGB", (128, 96), "black" if scene == "night" else "white")
    if scene == "black":
        image.paste("black", (0, 0, 128, 96))
    elif scene == "night":
        image.paste("white", (40, 40, 50, 50))
    elif scene == "pattern":
        for x in range(128):
            for y in range(96):
                image.putpixel((x, y), ((x * 19) % 256, (y * 23) % 256, (x * y) % 256))
    path = tmp_path / "frame.png"
    image.convert(mode).save(path)
    with Image.open(path) as original:
        expected = not archive.is_mostly_blank(original) and _is_valid_png(str(path))
    assert archive._archive_check(str(path), archive._frame_has_content) == expected


@pytest.mark.parametrize("tolerant", [False, True])
@pytest.mark.parametrize("damage", ["truncated", "crc"])
def test_combined_check_rejects_corruption(tmp_path, monkeypatch, tolerant, damage):
    from PIL import ImageFile

    path = tmp_path / "frame.png"
    Image.new("RGB", (32, 32), "red").save(path)
    data = bytearray(path.read_bytes())
    if damage == "truncated":
        data = data[:-20]
    else:
        start = data.index(b"IDAT")
        length = int.from_bytes(data[start - 4 : start], "big")
        data[start + 4 + length] ^= 1  # CRC corruption, pixels unchanged.
    path.write_bytes(data)
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", tolerant)
    assert not archive._archive_check(str(path), archive._frame_has_content)


def test_combined_result_reused_before_encoding(tmp_path, monkeypatch):
    path = tmp_path / "cam_20260928000000.png"
    Image.new("RGB", (32, 32), "red").save(path)
    time.sleep(1.05)
    check = Mock(wraps=archive._frame_has_content)
    monkeypatch.setattr(archive, "_frame_has_content", check)
    selected = archive._collect_new_frame_files(str(tmp_path), "cam", 0)
    assert selected == [str(path)]
    assert archive._archive_check(selected[0], archive._frame_has_content)
    assert check.call_count == 1
    # A replacement between selection and encode must never reuse the verdict.
    path.write_bytes(b"broken")
    assert not archive._archive_check(selected[0], archive._frame_has_content)
    assert check.call_count == 2
