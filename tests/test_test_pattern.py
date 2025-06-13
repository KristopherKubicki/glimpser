import datetime
import hashlib
import io
import json
import math
import os
import tempfile
import unittest
import unittest.mock

from PIL import Image

from app.utils.test_pattern import (
    _format_beats_time,
    _format_binary_time,
    _format_hex_time,
    _format_roman_time,
    _to_braille,
    encode_jpeg_with_metadata,
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

    def test_super_patches_and_zone_plate(self):
        width, height = 160, 160
        img = generate_test_pattern(width=width, height=height)

        bar_h = height // 16
        bars_total = bar_h * 2
        step_h = max(4, bar_h // 3)
        patch_y = bars_total + step_h + 2 + 4

        self.assertEqual(img.getpixel((4, patch_y)), (255, 255, 255))
        self.assertEqual(img.getpixel((width - 4, patch_y)), (0, 0, 0))

        cx, cy = width // 2, height // 2
        region = {
            img.getpixel((cx + dx, cy + dy))
            for dx in range(-4, 5)
            for dy in range(-4, 5)
        }
        self.assertGreater(len(region), 1)

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

    def test_date_overlay(self):
        class FixedDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2020, 1, 1, 12, 0, 0)

        with unittest.mock.patch(
            "app.utils.test_pattern.datetime.datetime", FixedDatetime
        ):
            img = generate_test_pattern(width=400, height=400)

        line_heights = [26, 26, 30, 22, 26]
        total_h = sum(line_heights) + 22 * (len(line_heights) - 1) + 30 * 2
        y_start = 400 // 2 - total_h // 2 + 20
        region = [
            img.getpixel((x, y))
            for x in range(30, 120)
            for y in range(y_start, y_start + 30)
        ]
        self.assertIn((160, 160, 160), region)
        self.assertTrue(any(pixel != (0, 0, 0) for pixel in region))

    def test_qr_code_overlay(self):
        stub = Image.new("RGBA", (12, 12), (255, 255, 255, 255))
        with (
            unittest.mock.patch(
                "app.utils.test_pattern._generate_qr_code", return_value=stub
            ),
            unittest.mock.patch("app.utils.test_pattern.time.time", return_value=0),
        ):
            img = generate_test_pattern(width=200, height=100)
        x = 200 - stub.width - 10 + stub.width // 2
        y = 100 - stub.height - 10 + stub.height // 2
        self.assertEqual(img.getpixel((x, y)), (204, 204, 204))

    def test_jpeg_metadata(self):
        img = generate_test_pattern(width=50, height=50)
        data = encode_jpeg_with_metadata(img)
        with Image.open(io.BytesIO(data)) as im:
            comment = im.info.get("comment")
        self.assertIsNotNone(comment)
        meta = json.loads(comment.decode())
        expected_hash = hashlib.sha256(img.tobytes()).hexdigest()[:8]
        self.assertEqual(meta["st2110_21_hash"], expected_hash)
        self.assertIn("smpte2086", meta)

    def test_moon_drawn(self):
        class FixedDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2020, 1, 1, 12, 0, 0)

        with unittest.mock.patch(
            "app.utils.test_pattern.datetime.datetime", FixedDatetime
        ):
            img = generate_test_pattern(width=200, height=100)

        bar_h = 100 // 16
        bars_total = bar_h * 2
        step_h = max(4, bar_h // 3)
        sun_r = min(200, 100) // 10
        horizon_y = 100 - bars_total - step_h - sun_r
        moon_r = sun_r // 2
        moon_cx = 200 * 3 // 4
        pixel = img.getpixel((moon_cx, horizon_y - moon_r // 2))
        self.assertNotEqual(pixel, (0, 0, 0))
        self.assertNotEqual(pixel, (80, 0, 80))


class TestTimeFormatHelpers(unittest.TestCase):
    def test_time_format_helpers(self):
        ts = "12:34:56"
        self.assertEqual(_format_binary_time(ts), "01100100010111000")
        self.assertEqual(_format_roman_time(ts), "XII:XXXIV:LVI")
        self.assertEqual(_format_hex_time(ts), "0C:22:38")
        self.assertEqual(_format_beats_time(ts), "@565")
        self.assertEqual(_to_braille(ts), "⠁⠃⠒⠉⠙⠒⠑⠋")


if __name__ == "__main__":
    unittest.main()
