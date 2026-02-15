# tests/test_llm.py

import datetime
import json
import time
import unittest
from unittest.mock import MagicMock, patch

from app.utils.llm import summarize

# Add the parent directory to the Python path to import the app module


class TestLLM(unittest.TestCase):
    def setUp(self):
        # Keep tests isolated: the in-memory cache is shared across tests within a worker.
        from app.utils import llm as llm_mod
        from app.utils import llm_cache

        llm_cache._cache.clear()
        llm_mod.last_429_error_time = None
        llm_mod._backoff_until = None

    @patch("app.utils.llm.request_with_retry")
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

        start = time.time()
        with patch("time.time", return_value=start):
            result = summarize("Test prompt (429)")

        ts = int(start + 0.5)
        expected_result = json.dumps(
            {ts: "Mock summary", ts + 5: "With multiple lines"}
        )
        self.assertEqual(json.loads(result), json.loads(expected_result))

        # Verify that the API was called with the correct parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertEqual(call_args["headers"]["Authorization"], "Bearer mock_api_key")
        self.assertEqual(call_args["json"]["model"], "mock_model_version")
        self.assertIn("Test prompt", str(call_args["json"]["messages"]))

    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.LOCAL_LLM_FALLBACK", False)
    @patch("app.utils.llm.CHATGPT_KEY", "mock_api_key")
    @patch("app.utils.llm.LLM_MODEL_VERSION", "mock_model_version")
    @patch("app.utils.llm.LLM_SUMMARY_PROMPT", "Mock summary prompt")
    def test_summarize_api_error(self, mock_post):
        # Mock an API error response
        mock_post.side_effect = Exception("API Error")

        result = summarize("Test prompt")

        data = json.loads(result)
        self.assertIn("Summarization delayed", list(data.values())[0])

    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.LOCAL_LLM_FALLBACK", False)
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

    @patch("app.utils.llm.summarize_with_ollama", return_value="Local summary line")
    @patch("app.utils.llm.LOCAL_LLM_TEXT_MODEL", "moondream")
    @patch("app.utils.llm.LOCAL_LLM_FALLBACK", True)
    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.CHATGPT_KEY", "mock_api_key")
    @patch("app.utils.llm.LLM_MODEL_VERSION", "mock_model_version")
    @patch("app.utils.llm.LLM_SUMMARY_PROMPT", "Mock summary prompt")
    def test_summarize_uses_local_fallback_on_429(self, mock_post, mock_local):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_post.return_value = mock_response

        result = summarize("Test prompt")

        data = json.loads(result)
        self.assertTrue(any("Local summary line" in v for v in data.values()))
        mock_local.assert_called_once()

    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.CHATGPT_KEY", "mock_api_key")
    @patch("app.utils.llm.LLM_MODEL_VERSION", "mock_model_version")
    @patch("app.utils.llm.LLM_SUMMARY_PROMPT", "Mock summary prompt")
    def test_summarize_with_history(self, mock_post):
        # Mock the successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Mock summary with history"}}],
            "usage": {"total_tokens": 150},
        }
        mock_post.return_value = mock_response

        start = time.time()
        with patch("time.time", return_value=start):
            result = summarize("Test prompt", history="Previous conversation")

        ts = int(start + 0.5)
        expected_result = json.dumps({ts: "Mock summary with history"})
        self.assertEqual(json.loads(result), json.loads(expected_result))

        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertIn("Previous conversation", str(call_args["json"]["messages"]))


if __name__ == "__main__":
    unittest.main()
