import unittest
import tempfile
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.image_processing import ChatGPTImageComparison


class TestImageProcessing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_path_a = os.path.join(self.temp_dir, "image_a.png")
        self.image_path_b = os.path.join(self.temp_dir, "image_b.png")

        # Create two simple test images
        image_a = Image.new("RGB", (100, 100), color="red")
        image_a.save(self.image_path_a)

        image_b = Image.new("RGB", (100, 100), color="blue")
        image_b.save(self.image_path_b)

        self.chatgpt_comparison = ChatGPTImageComparison()

    def tearDown(self):
        os.remove(self.image_path_a)
        os.remove(self.image_path_b)
        os.rmdir(self.temp_dir)

    def test_compare_images(self):
        prompt = "Compare these two images and describe the differences."
        result = self.chatgpt_comparison.compare_images(
            prompt, [self.image_path_a, self.image_path_b]
        )
        self.assertIsNotNone(result)
        self.assertIn("red", result.lower())
        self.assertIn("blue", result.lower())

    def test_compare_images_same(self):
        prompt = "Compare these two images and describe the differences."
        result = self.chatgpt_comparison.compare_images(
            prompt, [self.image_path_a, self.image_path_a]
        )
        self.assertIsNotNone(result)
        self.assertIn("identical", result.lower())

    def test_compare_images_invalid_path(self):
        prompt = "Compare these two images and describe the differences."
        invalid_path = os.path.join(self.temp_dir, "nonexistent.png")
        result = self.chatgpt_comparison.compare_images(
            prompt, [invalid_path, self.image_path_b]
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
