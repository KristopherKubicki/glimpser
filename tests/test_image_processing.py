import unittest
import os
import sys
import tempfile
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.screenshots import add_timestamp, remove_background, is_mostly_blank

class TestImageProcessing(unittest.TestCase):

    def test_add_timestamp(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            image_path = temp_file.name
        try:
            # Create a simple image and add a timestamp
            with Image.new("RGB", (100, 100), color="black") as img:
                img.save(image_path)
            add_timestamp(image_path, name="Test Image", invert=False)
            self.assertTrue(os.path.exists(image_path))
        finally:
            os.remove(image_path)

    def test_remove_background(self):
        # Create a test image with a non-background pixel
        with Image.new("RGBA", (100, 100), color=(14, 14, 14, 255)) as img:
            img.putpixel((50, 50), (255, 0, 0, 255))  # Add a non-background pixel
            result = remove_background(img)
            self.assertEqual(result.size, (100, 100))  # Ensure the size is correct
            self.assertEqual(result.getpixel((50, 50)), (255, 0, 0, 255))  # Check if non-background pixel is preserved
            self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))  # Check if background is removed

    def test_is_mostly_blank(self):
        # Test with a blank image
        with Image.new("RGB", (100, 100), color="white") as img:
            self.assertTrue(is_mostly_blank(img))

        # Test with a non-blank image
        with Image.new("RGB", (100, 100), color="white") as img:
            img.putpixel((50, 50), (0, 0, 0))  # Add a non-blank pixel
            self.assertFalse(is_mostly_blank(img))

        # Test with a dark image
        with Image.new("RGB", (100, 100), color="black") as img:
            self.assertTrue(is_mostly_blank(img))


if __name__ == '__main__':
    unittest.main()

