import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.screenshots import (
    remove_background,
    find_bounding_box,
    adjust_bbox_to_aspect_ratio,
    is_similar_color,
    is_mostly_blank,
    parse_url,
)
from PIL import Image


class TestScreenshots(unittest.TestCase):
    def setUp(self):
        # Create a sample image for testing
        self.test_image = Image.new("RGB", (100, 100), color="white")
        self.test_image_path = "test_image.png"
        self.test_image.save(self.test_image_path)

    def tearDown(self):
        # Clean up the test image
        if os.path.exists(self.test_image_path):
            os.remove(self.test_image_path)

    def test_remove_background(self):
        # Create a test image with a black border
        image = Image.new("RGB", (100, 100), color="white")
        draw = Image.Draw(image)
        draw.rectangle([0, 0, 99, 99], outline="black")

        result = remove_background(image)

        # Check if the result is not None and has the correct aspect ratio
        self.assertIsNotNone(result)
        self.assertEqual(result.width / result.height, 16 / 9)

    def test_find_bounding_box(self):
        # Create a test image with a black rectangle
        image = Image.new("RGB", (100, 100), color="white")
        draw = Image.Draw(image)
        draw.rectangle([20, 20, 80, 80], fill="black")

        bbox = find_bounding_box(image)

        # Check if the bounding box is correct
        self.assertEqual(bbox, (20, 20, 80, 80))

    def test_adjust_bbox_to_aspect_ratio(self):
        bbox = (20, 20, 80, 80)
        image_size = (100, 100)

        adjusted_bbox = adjust_bbox_to_aspect_ratio(bbox, image_size)

        # Check if the adjusted bounding box has the correct aspect ratio
        width = adjusted_bbox[2] - adjusted_bbox[0]
        height = adjusted_bbox[3] - adjusted_bbox[1]
        self.assertAlmostEqual(width / height, 16 / 9, places=2)

    def test_is_similar_color(self):
        self.assertTrue(is_similar_color((100, 100, 100), (105, 105, 105), 10))
        self.assertFalse(is_similar_color((100, 100, 100), (120, 120, 120), 10))

    def test_is_mostly_blank(self):
        # Create a mostly white image
        white_image = Image.new("RGB", (100, 100), color="white")
        self.assertTrue(is_mostly_blank(white_image))

        # Create a mostly black image
        black_image = Image.new("RGB", (100, 100), color="black")
        self.assertFalse(is_mostly_blank(black_image))

    def test_parse_url(self):
        domain, port = parse_url("http://example.com")
        self.assertEqual(domain, "example.com")
        self.assertEqual(port, 80)

        domain, port = parse_url("https://example.com:8080")
        self.assertEqual(domain, "example.com")
        self.assertEqual(port, 8080)


if __name__ == "__main__":
    unittest.main()
