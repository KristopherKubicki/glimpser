import os
import tempfile
import unittest

from PIL import Image

from app.utils.test_pattern import (
    _format_binary_time,
    _format_roman_time,
    _to_braille,
    generate_test_pattern,
    save_test_pattern,
)


class TestTestPattern(unittest.TestCase):
    def test_generate_size(self):
        img = generate_test_pattern(width=200, height=100, camera_name="CamA")
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (200, 100))

    def test_save(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "pattern.png")
            save_test_pattern(path, width=100, height=50)
            self.assertTrue(os.path.exists(path))
            with Image.open(path) as im:
                self.assertEqual(im.size, (100, 50))

    def test_grey_patch(self):
        width, height = 220, 110
        img = generate_test_pattern(width=width, height=height)
        self.assertEqual(img.size, (220, 110))
        # the patch is drawn as a mid-gray reference point
        self.assertEqual(img.getpixel((116, 58)), (118, 118, 118))


class TestTimeFormatHelpers(unittest.TestCase):
    def test_time_format_helpers(self):
        ts = "12:34:56"
        self.assertEqual(_format_binary_time(ts), "01100:100010:111000")
        self.assertEqual(_format_roman_time(ts), "XII:XXXIV:LVI")
        self.assertEqual(_to_braille(ts), "⠁⠃⠒⠉⠙⠒⠑⠋")


if __name__ == "__main__":
    unittest.main()
