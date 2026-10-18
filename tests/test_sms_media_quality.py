from PIL import Image

from app.utils import sms_media


def frame(root, name, color=(10, 40, 70)):
    path = root / name
    Image.new("RGB", (80, 60), color).save(path)
    return path


def test_clean_capture_replaces_captioned_and_rolling_copies(tmp_path):
    frame(tmp_path, "Beach_20261003120000.png")
    clean = frame(tmp_path, "Beach_20261003120000.png.clean.png")
    for name in [
        "last_clean.png",
        "last_motion.png",
        "prev_motion.png",
        "last_motion_caption.png",
        "last_caption.png",
        "latest_camera.png",
    ]:
        frame(tmp_path, name)
    assert sms_media._recent_frame_paths(tmp_path) == [clean]


def test_broken_clean_copy_falls_back_to_original(tmp_path):
    original = frame(tmp_path, "FrontDoor_001.png")
    (tmp_path / "FrontDoor_001.png.clean.png").write_bytes(b"broken")
    assert sms_media._recent_frame_paths(tmp_path) == [original]


def test_event_buffer_jpeg_sources_preserved(tmp_path):
    original = frame(tmp_path, "20261003120000.jpg")
    assert sms_media._recent_frame_paths(tmp_path, suffixes={".jpg"}) == [original]
