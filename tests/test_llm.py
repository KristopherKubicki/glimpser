import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.llm import summarize


class TestSummarize(unittest.TestCase):
    @patch("app.utils.llm.requests.post")
    def test_summarize(self, mock_post):
        # Mock the API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test summary"}}],
            "usage": {"total_tokens": 100},
        }
        mock_post.return_value = mock_response

        result = summarize("Test prompt", "Test history")

        self.assertIsNotNone(result)
        self.assertIn("Test summary", result)
        mock_post.assert_called_once()

    @patch("app.utils.llm.requests.post")
    def test_summarize_rate_limit(self, mock_post):
        # Simulate a rate limit error
        mock_post.side_effect = Exception("429 error")

        result = summarize("Test prompt")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
