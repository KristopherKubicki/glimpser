# tests/test_llm.py

import unittest
import sys
import os
import json
import datetime
from unittest.mock import patch, MagicMock

# Add the parent directory to the Python path to import the app module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.llm import summarize


class TestLLM(unittest.TestCase):
    @patch("app.utils.llm.requests.post")
    @patch("app.utils.llm.CHATGPT_KEY", "mock_api_key")
    @patch("app.utils.llm.LLM_MODEL_VERSION", "mock_model_version")
    @patch("app.utils.llm.LLM_SUMMARY_PROMPT", "Mock summary prompt")
    def test_summarize_success(self, mock_post):
        # Mock the successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Mock summary\nWith multiple lines"}}],
            "usage": {"total_tokens": 100},
        }
        mock_post.return_value = mock_response

        result = summarize("Test prompt")

        # Check if the result is as expected
        expected_result = json.dumps(
            {
                int(datetime.datetime.now().timestamp()): "Mock summary",
                int(datetime.datetime.now().timestamp()) + 5: "With multiple lines",
            }
        )
        self.assertEqual(json.loads(result), json.loads(expected_result))

        # Verify that the API was called with the correct parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertEqual(call_args["headers"]["Authorization"], "Bearer mock_api_key")
        self.assertEqual(call_args["json"]["model"], "mock_model_version")
        self.assertIn("Test prompt", str(call_args["json"]["messages"]))

    @patch("app.utils.llm.requests.post")
    def test_summarize_api_error(self, mock_post):
        # Mock an API error response
        mock_post.side_effect = Exception("API Error")

        result = summarize("Test prompt")

        # Check if the result is None when an error occurs
        self.assertIsNone(result)

    @patch("app.utils.llm.requests.post")
    @patch(
        "app.utils.llm.last_429_error_time",
        datetime.datetime.now() - datetime.timedelta(minutes=10),
    )
    def test_summarize_rate_limit(self, mock_post):
        result = summarize("Test prompt")

        # Check if the result is None due to recent rate limiting
        self.assertIsNone(result)

        # Verify that the API was not called
        mock_post.assert_not_called()

    @patch("app.utils.llm.requests.post")
    def test_summarize_with_history(self, mock_post):
        # Mock the successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Mock summary with history"}}],
            "usage": {"total_tokens": 150},
        }
        mock_post.return_value = mock_response

        result = summarize("Test prompt", history="Previous conversation")

        # Check if the result is as expected
        expected_result = json.dumps(
            {int(datetime.datetime.now().timestamp()): "Mock summary with history"}
        )
        self.assertEqual(json.loads(result), json.loads(expected_result))

        # Verify that the API was called with the correct parameters including history
        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertIn("Previous conversation", str(call_args["json"]["messages"]))


if __name__ == "__main__":
    unittest.main()
