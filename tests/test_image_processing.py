import unittest
import os
import sys
import tempfile
from PIL import Image
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.screenshots import add_timestamp, remove_background, is_mostly_blank, find_bounding_box, adjust_bbox_to_aspect_ratio, is_similar_color

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
        # Create a test image with a background color and a different color rectangle
        image = Image.new("RGB", (100, 100), color=(14, 14, 14))
        draw = Image.Draw(image)
        draw.rectangle([20, 20, 80, 80], fill=(255, 0, 0))

        # Apply remove_background function
        result = remove_background(image)

        # Check if the result is not None and has the correct size
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (100, 100))

        # Check if the background is removed (should be transparent or white)
        background_color = result.getpixel((0, 0))
        self.assertTrue(background_color in [(0, 0, 0, 0), (255, 255, 255)])

        # Check if the red rectangle is preserved
        center_color = result.getpixel((50, 50))
        self.assertEqual(center_color[:3], (255, 0, 0))

    def test_find_bounding_box(self):
        # Create a test image with a background color and a different color rectangle
        image = Image.new("RGB", (100, 100), color=(14, 14, 14))
        draw = Image.Draw(image)
        draw.rectangle([20, 20, 80, 80], fill=(255, 0, 0))

        # Find the bounding box
        bbox = find_bounding_box(image)

        # Check if the bounding box is correct
        self.assertEqual(bbox, (20, 20, 80, 80))

    def test_adjust_bbox_to_aspect_ratio(self):
        # Test case 1: Bounding box is already 16:9
        bbox = (0, 0, 1600, 900)
        image_size = (1920, 1080)
        adjusted_bbox = adjust_bbox_to_aspect_ratio(bbox, image_size)
        self.assertEqual(adjusted_bbox, bbox)

        # Test case 2: Bounding box is taller than 16:9
        bbox = (0, 0, 800, 900)
        adjusted_bbox = adjust_bbox_to_aspect_ratio(bbox, image_size)
        self.assertEqual(adjusted_bbox[3] - adjusted_bbox[1], 450)  # Height should be adjusted

        # Test case 3: Bounding box is wider than 16:9
        bbox = (0, 0, 1600, 800)
        adjusted_bbox = adjust_bbox_to_aspect_ratio(bbox, image_size)
        self.assertEqual(adjusted_bbox[2] - adjusted_bbox[0], 1600)  # Width should remain the same

    def test_is_similar_color(self):
        color1 = (100, 100, 100)
        color2 = (110, 110, 110)
        color3 = (150, 150, 150)

        self.assertTrue(is_similar_color(color1, color2, threshold=15))
        self.assertFalse(is_similar_color(color1, color3, threshold=15))

    def test_is_mostly_blank(self):
        # Test case 1: Completely white image
        white_image = Image.new("RGB", (100, 100), color=(255, 255, 255))
        self.assertTrue(is_mostly_blank(white_image))

        # Test case 2: Completely black image
        black_image = Image.new("RGB", (100, 100), color=(0, 0, 0))
        self.assertTrue(is_mostly_blank(black_image))

        # Test case 3: Image with some content
        content_image = Image.new("RGB", (100, 100), color=(255, 255, 255))
        draw = Image.Draw(content_image)
        draw.rectangle([20, 20, 80, 80], fill=(0, 0, 0))
        self.assertFalse(is_mostly_blank(content_image))

        # Test case 4: Image with minimal content
        minimal_content_image = Image.new("RGB", (100, 100), color=(255, 255, 255))
        draw = Image.Draw(minimal_content_image)
        draw.rectangle([45, 45, 55, 55], fill=(0, 0, 0))
        self.assertTrue(is_mostly_blank(minimal_content_image))


if __name__ == '__main__':
    unittest.main()

