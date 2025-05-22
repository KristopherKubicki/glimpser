import os
import tempfile
import shutil
import pytest

@pytest.fixture
def temp_media_dirs(monkeypatch):
    screenshot_dir = tempfile.mkdtemp()
    video_dir = tempfile.mkdtemp()
    monkeypatch.setattr('app.config.SCREENSHOT_DIRECTORY', screenshot_dir, raising=False)
    monkeypatch.setattr('app.config.VIDEO_DIRECTORY', video_dir, raising=False)
    yield {'screenshots': screenshot_dir, 'videos': video_dir}
    shutil.rmtree(screenshot_dir, ignore_errors=True)
    shutil.rmtree(video_dir, ignore_errors=True)
