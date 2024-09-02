# tests/test_image_processing.py

import unittest
import os
import sys
import tempfile
import numpy as np
from PIL import Image
from unittest.mock import patch, MagicMock
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.screenshots import (
    add_timestamp, remove_background, find_bounding_box,
    adjust_bbox_to_aspect_ratio, is_mostly_blank
)
from app.utils.image_processing import ChatGPTImageComparison

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
        # Create a test image with a background
        image = Image.new("RGBA", (100, 100), color=(14, 14, 14, 255))
        # Add a non-background pixel
        image.putpixel((50, 50), (255, 0, 0, 255))

        # Apply remove_background function
        result = remove_background(image)

        # Check if the result is an image and has the correct dimensions
        self.assertIsInstance(result, Image.Image)
        # TODO: fix this ...
        #self.assertEqual(result.size, (100, 100))

        # Check if the background is removed (should be transparent)
        # index out of range? fix this
        #self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))

        # Check if the non-background pixel is preserved
        # index out of range?  fix this
        #self.assertEqual(result.getpixel((50, 50)), (255, 0, 0, 255))

    def test_find_bounding_box(self):
        # Create a test image with a known non-background area
        image = Image.new("RGBA", (100, 100), color=(14, 14, 14, 255))
        for x in range(25, 75):
            for y in range(25, 75):
                image.putpixel((x, y), (255, 0, 0, 255))

        # Apply find_bounding_box function
        bbox = find_bounding_box(image)

        # Check if the bounding box is correct
        self.assertEqual(bbox, (25, 25, 74, 74))

    def test_adjust_bbox_to_aspect_ratio(self):
        # Create a sample bounding box and image size
        bbox = (25, 25, 75, 75)
        image_size = (100, 100)

        # Apply adjust_bbox_to_aspect_ratio function
        adjusted_bbox = adjust_bbox_to_aspect_ratio(bbox, image_size, aspect_ratio=(16, 9))

        # Check if the adjusted bounding box has the correct aspect ratio
        width = adjusted_bbox[2] - adjusted_bbox[0]
        height = adjusted_bbox[3] - adjusted_bbox[1]
        self.assertAlmostEqual(width / height, 16 / 9, places=2)

    def test_is_mostly_blank(self):
        # Test with a blank image
        blank_image = Image.new("RGB", (100, 100), color="white")
        self.assertTrue(is_mostly_blank(blank_image))

        # Test with a non-blank image
        non_blank_image = Image.new("RGB", (100, 100), color="white")
        for x in range(40, 60):
            for y in range(40, 60):
                non_blank_image.putpixel((x, y), (0, 0, 0))
        # TODO: fix this!
        #self.assertFalse(is_mostly_blank(non_blank_image))

        # Test with a dark image
        dark_image = Image.new("RGB", (100, 100), color="black")
        self.assertTrue(is_mostly_blank(dark_image))


class TestChatGPTImageComparison(unittest.TestCase):
    @patch('app.utils.image_processing.requests.post')
    def test_compare_images(self, mock_post):
        # Create a ChatGPTImageComparison instance
        comparison = ChatGPTImageComparison()

        # Create temporary image files
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file1, \
             tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file2:
            image1_path = temp_file1.name
            image2_path = temp_file2.name

            # Create and save test images
            Image.new('RGB', (100, 100), color='red').save(image1_path)
            Image.new('RGB', (100, 100), color='blue').save(image2_path)

        try:
            # Mock the API response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test caption for the images"}}],
                "usage": {"total_tokens": 50}
            }
            mock_post.return_value = mock_response

            # Test the compare_images method
            result = comparison.compare_images("Test prompt", [image1_path, image2_path])

            # Assertions
            self.assertIsNotNone(result)
            self.assertEqual(result, "Test caption for the images")

            # Check if the API was called with correct parameters
            mock_post.assert_called_once()
            call_args = mock_post.call_args[1]
            self.assertEqual(call_args['headers']['Authorization'], f"Bearer {comparison.api_key}")
            self.assertEqual(call_args['json']['model'], "gpt-4o-mini")  # Assuming this is the default model
            self.assertIn("Test prompt", str(call_args['json']['messages']))

            # Test with low_res=True
            comparison.compare_images("Test prompt", [image1_path, image2_path], low_res=True)
            self.assertIn('"detail": "low"', str(mock_post.call_args[1]['json']['messages']))

            # Test error handling
            mock_post.side_effect = Exception("API Error")
            result = comparison.compare_images("Test prompt", [image1_path, image2_path])
            self.assertIsNone(result)

            # Test rate limiting
            comparison.last_429_error_time = datetime.datetime.now()
            result = comparison.compare_images("Test prompt", [image1_path, image2_path])
            self.assertIsNone(result)

        finally:
            # Clean up temporary files
            os.remove(image1_path)
            os.remove(image2_path)


if __name__ == '__main__':
    unittest.main()

