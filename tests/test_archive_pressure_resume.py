"""Pressure deferrals preserve the next camera, even for unlimited batches."""

import json

import pytest

from app.utils import video_archiver as archive


@pytest.mark.parametrize("batch_size", [0, 2, 99])
def test_midbatch_pressure_resumes_at_unprocessed_camera(
    tmp_path, monkeypatch, batch_size
):
    frames, videos = tmp_path / "frames", tmp_path / "videos"
    for name in ("camera_a", "camera_b", "camera_c"):
        (frames / name).mkdir(parents=True)
    monkeypatch.setattr(archive, "SCREENSHOT_DIRECTORY", str(frames))
    monkeypatch.setattr(archive, "VIDEO_DIRECTORY", str(videos))
    monkeypatch.setattr(archive, "ARCHIVE_BATCH_SIZE", batch_size)
    readings = iter([False, False, True])
    monkeypatch.setattr(archive, "_archive_io_pressure_high", lambda: next(readings))
    attempted = []
    monkeypatch.setattr(
        archive, "compile_to_video", lambda camera, video: attempted.append(camera)
    )
    archive.archive_screenshots()
    cursor = videos / archive.ARCHIVE_CURSOR_FILENAME
    assert attempted == [str(frames / "camera_a")]
    assert json.loads(cursor.read_text())["index"] == 1

    # An entirely deferred run must not advance the saved cursor.
    monkeypatch.setattr(archive, "_archive_io_pressure_high", lambda: True)
    before = cursor.read_bytes()
    archive.archive_screenshots()
    assert cursor.read_bytes() == before

    monkeypatch.setattr(archive, "_archive_io_pressure_high", lambda: False)
    archive.archive_screenshots()
    assert attempted[1:3] == [str(frames / "camera_b"), str(frames / "camera_c")]
    assert json.loads(cursor.read_text())["index"] == (1 + min(batch_size or 3, 3)) % 3
