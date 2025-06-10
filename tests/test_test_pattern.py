import unittest
import os
import tempfile

from PIL import Image

from app.utils.test_pattern import (
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


if __name__ == "__main__":
    unittest.main()
