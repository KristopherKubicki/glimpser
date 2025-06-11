import os
import sys
import tempfile

from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.qrcode_overlay import add_micro_barcode, generate_micro_barcode


def test_generate_micro_barcode_length():
    pattern = generate_micro_barcode("abc")
    assert len(pattern) == 64


def test_add_micro_barcode_overlay():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        Image.new("RGB", (50, 50), (255, 255, 255)).save(tmp.name)
        add_micro_barcode(tmp.name, "test")
        with Image.open(tmp.name) as img:
            # a pixel in the overlay region should not be background white
            assert img.getpixel((33, 33)) != (255, 255, 255)
    os.unlink(tmp.name)
