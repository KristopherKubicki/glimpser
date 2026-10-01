"""Faster capture encoding must preserve pixels and atomic publication."""

import random

import pytest
from PIL import Image

from app.utils.image_utils import save_image


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P", "I;16"])
def test_capture_png_preserves_pixels_and_mode(tmp_path, mode):
    bands = {"RGB": 3, "RGBA": 4, "L": 1, "P": 1, "I;16": 2}[mode]
    data = random.Random(42).randbytes(64 * 48 * bands)
    image = Image.frombytes(mode, (64, 48), data)
    if mode == "P":
        image.putpalette([value for value in range(256) for _ in range(3)])
        image.info["transparency"] = 0
    path = tmp_path / "frame.png"
    save_image(image, str(path))
    with Image.open(path) as saved:
        assert saved.size == (64, 48)
        assert saved.tobytes() == data
        if mode == "P":
            assert saved.info["transparency"] == 0
    assert list(tmp_path.iterdir()) == [path]
