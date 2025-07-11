import os
import time
from unittest.mock import patch

from app import routes


def test_generate_removes_invalid_image_and_cache(tmp_path):
    shots = tmp_path / "cam"
    shots.mkdir()
    bad_png = shots / "cap1.png"
    bad_png.write_bytes(b"bad")

    last_jpg = tmp_path / "latest_camera.jpg"
    last_jpg.write_bytes(b"old")
    old = time.time() - 5
    os.utime(last_jpg, (old, old))

    with patch("app.routes.SCREENSHOT_DIRECTORY", str(tmp_path)):
        with patch("app.routes.template_manager.get_templates", return_value={"cam": {"name": "cam"}}):
            with patch("os.listdir", side_effect=lambda p: ["cap1.png"] if p.endswith("cam") else []):
                with patch("os.path.isfile", side_effect=lambda p: p.endswith("cap1.png")):
                    with patch("os.path.getctime", side_effect=lambda p: time.time() if p.endswith("cap1.png") else 0):
                        gen = routes.generate(camera="cam")
                        frame = next(gen)

    assert isinstance(frame, (bytes, bytearray))
    assert not bad_png.exists()
    assert not last_jpg.exists()
