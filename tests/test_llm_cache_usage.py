import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.utils import image_processing, llm_cache
from app.utils.llm import summarize


class TestLLMCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.tmpdir, "cache.json")
        self.patcher = patch("app.utils.llm_cache.CACHE_PATH", self.cache_file)
        self.patcher.start()
        llm_cache._cache.clear()
        llm_cache._persist_cache()

    def tearDown(self):
        self.patcher.stop()
        try:
            os.remove(self.cache_file)
        except Exception:
            pass
        os.rmdir(self.tmpdir)

    @patch("app.utils.llm.request_with_retry")
    @patch("app.utils.llm.CHATGPT_KEY", "k")
    @patch("app.utils.llm.LLM_MODEL_VERSION", "gpt")
    @patch("app.utils.llm.LLM_SUMMARY_PROMPT", "prompt")
    def test_summarize_uses_cache(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "one"}}],
            "usage": {"total_tokens": 5},
        }
        mock_post.return_value = mock_response

        first = summarize("p")
        second = summarize("p")

        self.assertEqual(first, second)
        self.assertEqual(mock_post.call_count, 1)

    @patch("app.utils.image_processing.ChatGPTImageComparison.compare_images")
    @patch("app.utils.image_processing.os.path.exists", return_value=True)
    @patch("app.utils.image_processing.CHATGPT_KEY", "k")
    def test_chatgpt_compare_uses_cache(self, mock_exists, mock_compare):
        mock_compare.return_value = ("ok", 5)
        result1 = image_processing.chatgpt_compare("p", ["img.png"])
        result2 = image_processing.chatgpt_compare("p", ["img.png"])
        self.assertEqual(result1, result2)
        mock_compare.assert_called_once()


if __name__ == "__main__":
    unittest.main()
