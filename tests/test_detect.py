import unittest
import os
import sys
import tempfile
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.detect import calculate_difference_fast


class TestDetect(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def create_image(self, size, color):
        image = Image.new("RGB", size, color=color)
        path = os.path.join(self.temp_dir, f"{color}_image.png")
        image.save(path)
        return path

    def test_identical_images(self):
        path = self.create_image((100, 100), "white")
        difference = calculate_difference_fast(path, path)
        self.assertAlmostEqual(difference, 0.0, places=2)

    def test_completely_different_images(self):
        white_path = self.create_image((100, 100), "white")
        black_path = self.create_image((100, 100), "black")
        difference = calculate_difference_fast(white_path, black_path)
        self.assertAlmostEqual(difference, 1.0, places=2)

    def test_slightly_different_images(self):
        # Create a mostly white image
        img1 = Image.new("RGB", (100, 100), color="white")
        img1_path = os.path.join(self.temp_dir, "mostly_white.png")
        img1.save(img1_path)

        # Create a similar image with a small black square
        img2 = Image.new("RGB", (100, 100), color="white")
        img2.paste(Image.new("RGB", (10, 10), color="black"), (45, 45))
        img2_path = os.path.join(self.temp_dir, "mostly_white_with_black_square.png")
        img2.save(img2_path)

        difference = calculate_difference_fast(img1_path, img2_path)
        # The difference should be small but not zero
        self.assertGreater(difference, 0.0)
        self.assertLess(difference, 0.1)

    def test_different_sized_images(self):
        img1_path = self.create_image((100, 100), "white")
        img2_path = self.create_image((200, 200), "white")
        difference = calculate_difference_fast(img1_path, img2_path)
        # Despite different sizes, the images are both white, so the difference should be very small
        self.assertAlmostEqual(difference, 0.0, places=2)

    def test_grayscale_images(self):
        img1 = Image.new("L", (100, 100), color=100)  # Medium gray
        img1_path = os.path.join(self.temp_dir, "gray1.png")
        img1.save(img1_path)

        img2 = Image.new("L", (100, 100), color=200)  # Light gray
        img2_path = os.path.join(self.temp_dir, "gray2.png")
        img2.save(img2_path)

        difference = calculate_difference_fast(img1_path, img2_path)
        # The difference should be significant but not 1.0
        self.assertGreater(difference, 0.3)
        self.assertLess(difference, 0.7)

    def test_invalid_image_path(self):
        valid_path = self.create_image((100, 100), "white")
        invalid_path = os.path.join(self.temp_dir, "non_existent_image.png")

        result = calculate_difference_fast(valid_path, invalid_path)
        self.assertIsNone(result, "Expected None for invalid image path")

        result = calculate_difference_fast(invalid_path, valid_path)
        self.assertIsNone(result, "Expected None for invalid image path")

        result = calculate_difference_fast(invalid_path, invalid_path)
        self.assertIsNone(result, "Expected None for invalid image path")


if __name__ == "__main__":
    unittest.main()
