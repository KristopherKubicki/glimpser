import os
import sys
import tempfile
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.qrcode_overlay import generate_micro_qr, add_micro_qr


def test_generate_micro_qr_size():
    matrix = generate_micro_qr("abc")
    assert len(matrix) == 8
    assert len(matrix[0]) == 8


def test_add_micro_qr_overlay():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        Image.new("RGB", (50, 50), (255, 255, 255)).save(tmp.name)
        add_micro_qr(tmp.name, "test")
        with Image.open(tmp.name) as img:
            # top-left pixel of the overlay should be dark
            assert img.getpixel((33, 33)) != (255, 255, 255)
    os.unlink(tmp.name)
