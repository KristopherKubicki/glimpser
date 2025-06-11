import os
import tempfile
import unittest

from PIL import Image

from app.utils.test_pattern import (
    generate_geometric_test_pattern,
    generate_indian_head_test_pattern,
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

    def test_indian_head_size(self):
        img = generate_indian_head_test_pattern(width=150, height=150)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (150, 150))

    def test_geometric_size(self):
        img = generate_geometric_test_pattern(width=120, height=120, tiles=5)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (120, 120))

    def test_minibar_colors(self):
        width, height = 200, 100
        img = generate_test_pattern(width=width, height=height)
        bar_h = height // 6
        mini_w = max(2, width // 100)
        mini_h = bar_h // 4
        x_start = width - mini_w * 14 - 10
        y_start = 2 + mini_h // 2
        colors = [
            (191, 191, 191),
            (191, 191, 0),
            (0, 191, 191),
            (0, 191, 0),
            (191, 0, 191),
            (191, 0, 0),
            (0, 0, 191),
            (0, 0, 0),
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (0, 255, 255),
            (255, 0, 255),
            (255, 255, 0),
        ]
        for idx, expected in enumerate(colors):
            px = img.getpixel((x_start + idx * mini_w + mini_w // 2, y_start))
            self.assertEqual(px, expected)


if __name__ == "__main__":
    unittest.main()
