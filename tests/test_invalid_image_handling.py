from unittest.mock import patch
from app import routes


def test_generate_handles_invalid_image(tmp_path):
    shots = tmp_path / "cam"
    shots.mkdir()
    target = shots / "cap1.png"
    target.write_bytes(b"x")

    with patch("app.routes.SCREENSHOT_DIRECTORY", str(tmp_path)):
        with patch("os.listdir", return_value=["cap1.png"]):
            with patch("os.path.isfile", return_value=True):
                with patch("os.path.getctime", return_value=0):
                    with patch(
                        "app.routes.screenshots._is_valid_png", return_value=False
                    ):
                        gen = routes.generate(camera="cam")
                        frame = next(gen)
                        assert isinstance(frame, (bytes, bytearray))
