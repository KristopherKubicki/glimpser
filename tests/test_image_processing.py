# Integration tests for image processing utilities and ChatGPT comparison

import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from app.utils.image_processing import ChatGPTImageComparison, chatgpt_compare
from app.utils.screenshots import (
    add_timestamp,
    adjust_bbox_to_aspect_ratio,
    find_bounding_box,
    is_mostly_blank,
    remove_background,
)


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

        for x in range(20, 80):
            for y in range(20, 80):
                image.putpixel((x, y), (255, 0, 0, 255))
        result = remove_background(image)

        self.assertIsInstance(result, Image.Image)
        ratio = result.size[0] / result.size[1]
        self.assertAlmostEqual(ratio, 16 / 9, delta=0.15)
        self.assertEqual(
            result.getpixel((result.width // 2, result.height // 2))[:3],
            (255, 0, 0),
        )

    def test_remove_background_white_border(self):
        image = Image.new("RGBA", (100, 100), color=(255, 255, 255, 255))
        image.putpixel((50, 50), (0, 0, 0, 255))
        result = remove_background(image)
        self.assertIsInstance(result, Image.Image)

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
        adjusted_bbox = adjust_bbox_to_aspect_ratio(
            bbox, image_size, aspect_ratio=(16, 9)
        )

        # Check if the adjusted bounding box has the correct aspect ratio
        width = adjusted_bbox[2] - adjusted_bbox[0]
        height = adjusted_bbox[3] - adjusted_bbox[1]
        self.assertAlmostEqual(width / height, 16 / 9, places=2)

    def test_is_mostly_blank(self):
        # Test with a blank image
        blank_image = Image.new("RGB", (100, 100), color="white")
        self.assertTrue(is_mostly_blank(blank_image))

        # Test with a non-blank image (large dark region)
        non_blank_image = Image.new("RGB", (100, 100), color="white")
        for x in range(25, 75):
            for y in range(25, 75):
                non_blank_image.putpixel((x, y), (0, 0, 0))
        self.assertFalse(is_mostly_blank(non_blank_image))

        # Test with a dark image
        dark_image = Image.new("RGB", (100, 100), color="black")
        self.assertTrue(is_mostly_blank(dark_image))


class TestChatGPTImageComparison(unittest.TestCase):
    @patch("app.utils.image_processing.request_with_retry")
    @patch("app.utils.image_processing.CHATGPT_KEY", "k")
    def test_compare_images(self, mock_post):
        # Create a ChatGPTImageComparison instance
        comparison = ChatGPTImageComparison()

        # Create temporary image files
        with (
            tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file1,
            tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file2,
        ):
            image1_path = temp_file1.name
            image2_path = temp_file2.name

            # Create and save test images
            Image.new("RGB", (100, 100), color="red").save(image1_path)
            Image.new("RGB", (100, 100), color="blue").save(image2_path)

        try:
            # Mock the API response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test caption for the images"}}],
                "usage": {"total_tokens": 50},
            }
            mock_post.return_value = mock_response

            # Test the compare_images method
            result, tokens = comparison.compare_images(
                "Test prompt", [image1_path, image2_path]
            )

            # Assertions
            self.assertIsNotNone(result)
            self.assertEqual(result, "Test caption for the images")
            self.assertEqual(tokens, 50)

            # Check if the API was called with correct parameters
            mock_post.assert_called_once()
            call_args = mock_post.call_args[1]
            self.assertEqual(
                call_args["headers"]["Authorization"], f"Bearer {comparison.api_key}"
            )
            self.assertEqual(
                call_args["json"]["model"], "gpt-4.1-mini"
            )  # Assuming this is the default model
            self.assertIn("Test prompt", str(call_args["json"]["messages"]))

            # Test with low_res=True
            comparison.compare_images(
                "Test prompt", [image1_path, image2_path], low_res=True
            )
            self.assertIn(
                "'detail': 'low'", str(mock_post.call_args[1]["json"]["messages"])
            )

            # Test error handling
            mock_post.side_effect = Exception("API Error")
            result, tokens = comparison.compare_images(
                "Test prompt", [image1_path, image2_path]
            )
            self.assertIsNone(result)
            self.assertEqual(tokens, 0)

            # Test rate limiting
            comparison.last_429_error_time = datetime.datetime.now()
            result, tokens = comparison.compare_images(
                "Test prompt", [image1_path, image2_path]
            )
            self.assertIsNone(result)
            self.assertEqual(tokens, 0)

        finally:
            # Clean up temporary files
            os.remove(image1_path)
            os.remove(image2_path)


class TestChatGPTCompareIntegration(unittest.TestCase):
    @patch("app.utils.image_processing.os.path.exists", return_value=True)
    @patch("app.utils.image_processing.CHATGPT_KEY", "k")
    @patch("app.utils.template_manager.record_llm_usage")
    @patch("app.utils.llm_cache.store")
    @patch("app.utils.llm_cache.get")
    @patch.object(ChatGPTImageComparison, "compare_images")
    def test_chatgpt_compare_uses_cache(
        self, mock_compare, mock_get, mock_store, mock_record, mock_exists
    ):
        mock_get.return_value = {"response": "cached", "tokens": 3}
        result = chatgpt_compare("Prompt", ["img.png"], template_name="cam1")
        self.assertEqual(result, "cached")
        mock_compare.assert_not_called()
        mock_store.assert_not_called()
        mock_record.assert_called_once_with("cam1", 3)

    @patch("app.utils.image_processing.os.path.exists", return_value=True)
    @patch("app.utils.image_processing.CHATGPT_KEY", "k")
    @patch("app.utils.template_manager.record_llm_usage")
    @patch("app.utils.llm_cache.store")
    @patch("app.utils.llm_cache.get", return_value=None)
    @patch.object(ChatGPTImageComparison, "compare_images")
    def test_chatgpt_compare_calls_api(
        self, mock_compare, mock_get, mock_store, mock_record, mock_exists
    ):
        mock_compare.return_value = ("result", 5)
        result = chatgpt_compare("Prompt", ["img.png"], template_name="cam1")
        self.assertEqual(result, "result")
        mock_compare.assert_called_once()
        mock_store.assert_called_once_with("Prompt", "result", 5, ["img.png"])
        mock_record.assert_called_once_with("cam1", 5)


class TestCleanCaption(unittest.TestCase):
    def test_clean_caption_removes_headers_and_formatting(self):
        from app.utils.image_processing import clean_caption

        self.assertEqual(
            clean_caption("Caption: **A bird**"),
            "A bird",
        )

    def test_clean_caption_handles_title(self):
        from app.utils.image_processing import clean_caption

        self.assertEqual(clean_caption("Title: **Scene**"), "Scene")


if __name__ == "__main__":
    unittest.main()
