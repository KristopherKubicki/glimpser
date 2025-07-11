import os
from unittest.mock import patch

from app import routes


def test_generate_handles_deleted_file(tmp_path):
    shots = tmp_path / "cam"
    shots.mkdir()
    target = shots / "cap1.png"
    target.write_bytes(b"x")

    with patch("app.routes.SCREENSHOT_DIRECTORY", str(tmp_path)):
        with patch("os.listdir", return_value=["cap1.png"]):
            with patch("os.path.isfile", return_value=True):
                with patch("os.path.getctime", side_effect=FileNotFoundError):
                    gen = routes.generate(camera="cam")
                    frame = next(gen)
                    assert isinstance(frame, (bytes, bytearray))
