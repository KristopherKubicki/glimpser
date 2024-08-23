import unittest
import tempfile
import os
import sys
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.detect import calculate_difference_fast
from app.utils.image_processing import ChatGPTImageComparison

class TestImageComparison(unittest.TestCase):
    def setUp(self):
        # Create two temporary image files for testing
        self.temp_dir = tempfile.mkdtemp()
        self.image_path_a = os.path.join(self.temp_dir, "image_a.png")
        self.image_path_b = os.path.join(self.temp_dir, "image_b.png")

        # Create a simple 100x100 black image
        image_a = Image.new("RGB", (100, 100), color="black")
        image_a.save(self.image_path_a)

        # Create a simple 100x100 white image
        image_b = Image.new("RGB", (100, 100), color="white")
        image_b.save(self.image_path_b)

    def tearDown(self):
        # Clean up temporary files
        os.remove(self.image_path_a)
        os.remove(self.image_path_b)
        os.rmdir(self.temp_dir)

    def test_calculate_difference_fast(self):
        # Test with two different images
        difference = calculate_difference_fast(self.image_path_a, self.image_path_b)
        self.assertAlmostEqual(difference, 1.0, places=2)

        # Test with the same image
        difference = calculate_difference_fast(self.image_path_a, self.image_path_a)
        self.assertAlmostEqual(difference, 0.0, places=2)

    @patch('app.utils.image_processing.requests.post')
    def test_chatgpt_image_comparison(self, mock_post):
        # Mock the API response
        mock_response = unittest.mock.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {"total_tokens": 10}
        }
        mock_post.return_value = mock_response

        # Create an instance of ChatGPTImageComparison
        chatgpt = ChatGPTImageComparison()

        # Test the compare_images method
        result = chatgpt.compare_images("Test prompt", [self.image_path_a, self.image_path_b])

        # Assert that the method returns the expected result
        self.assertEqual(result, "Test response")

        # Assert that the API was called with the correct arguments
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("json", kwargs)
        self.assertIn("messages", kwargs["json"])
        self.assertEqual(len(kwargs["json"]["messages"]), 4)  # System message, user prompt, and two images

if __name__ == "__main__":
    unittest.main()
