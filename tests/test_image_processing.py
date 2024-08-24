import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.image_processing import ChatGPTImageComparison, chatgpt_compare

class TestChatGPTImageComparison(unittest.TestCase):

    @patch('app.utils.image_processing.requests.post')
    def test_compare_images(self, mock_post):
        # Mock the API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test comparison result"}}],
            "usage": {"total_tokens": 100}
        }
        mock_post.return_value = mock_response

        comparison = ChatGPTImageComparison()
        result = comparison.compare_images("Test prompt", ["test_image1.jpg", "test_image2.jpg"])

        self.assertEqual(result, "Test comparison result")
        mock_post.assert_called_once()

class TestChatgptCompare(unittest.TestCase):

    @patch('app.utils.image_processing.ChatGPTImageComparison.compare_images')
    def test_chatgpt_compare(self, mock_compare_images):
        mock_compare_images.return_value = "Test comparison result"

        result = chatgpt_compare(["test_image1.jpg", "test_image2.jpg"], "Test prompt")

        self.assertEqual(result, "Test comparison result")
        mock_compare_images.assert_called_once_with("Test prompt", ["test_image1.jpg", "test_image2.jpg"])

if __name__ == '__main__':
    unittest.main()