import datetime
import math
import os
import tempfile
import unittest
import unittest.mock

from PIL import Image

from app.utils.test_pattern import (
    _format_beats_time,
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

    def test_spinner_overlay(self):
        img = generate_test_pattern(width=120, height=60, spinner="⠋")
        region = [img.getpixel((x, y)) for x in range(80, 95) for y in range(20, 35)]
        self.assertIn((255, 255, 255), region)

    def test_clock_hand_drawn(self):
        class FixedDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2020, 1, 1, 0, 0, 15)

        with unittest.mock.patch(
            "app.utils.test_pattern.datetime.datetime", FixedDatetime
        ):
            img = generate_test_pattern(width=120, height=60)
        cx, cy = 60, 30
        hand_len = min(120, 60) * 0.4
        end_x = int(round(cx + hand_len * math.cos(math.radians((15 / 60) * 360 - 90))))
        end_y = int(round(cy + hand_len * math.sin(math.radians((15 / 60) * 360 - 90))))
        end_x = min(img.width - 1, end_x)
        end_y = min(img.height - 1, end_y)
        self.assertEqual(img.getpixel((end_x, end_y)), (255, 255, 255))


class TestTimeFormatHelpers(unittest.TestCase):
    def test_time_format_helpers(self):
        ts = "12:34:56"
        self.assertEqual(_format_binary_time(ts), "01100:100010:111000")
        self.assertEqual(_format_roman_time(ts), "XII:XXXIV:LVI")
        self.assertEqual(_format_beats_time(ts), "@565")
        self.assertEqual(_to_braille(ts), "⠁⠃⠒⠉⠙⠒⠑⠋")


if __name__ == "__main__":
    unittest.main()
