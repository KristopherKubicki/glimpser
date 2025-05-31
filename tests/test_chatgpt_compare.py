import os
import sys
from unittest.mock import patch
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.image_processing import chatgpt_compare


class TestChatGPTCompare(unittest.TestCase):
    @patch("app.utils.image_processing.os.path.exists", return_value=False)
    def test_missing_image(self, mock_exists):
        result = chatgpt_compare("p", ["missing.png"])
        self.assertEqual(result, "Missing image")

    @patch("app.utils.image_processing.ChatGPTImageComparison.compare_images")
    @patch("app.utils.image_processing.os.path.exists", return_value=True)
    @patch("app.utils.image_processing.CHATGPT_KEY", "")
    def test_missing_key(self, mock_exists, mock_compare):
        result = chatgpt_compare("p", ["img.png"])
        self.assertEqual(result, "Missing ChatGPT key")
        mock_compare.assert_not_called()

    @patch("app.utils.image_processing.ChatGPTImageComparison.compare_images")
    @patch("app.utils.template_manager.record_llm_usage")
    @patch("app.utils.image_processing.os.path.exists", return_value=True)
    @patch("app.utils.image_processing.CHATGPT_KEY", "k")
    def test_success_records_usage(self, mock_exists, mock_record, mock_compare):
        mock_compare.return_value = ("ok", 5)
        result = chatgpt_compare("p", ["img.png"], template_name="cam1")
        self.assertEqual(result, "ok")
        mock_compare.assert_called_once()
        mock_record.assert_called_once_with("cam1", 5)


if __name__ == "__main__":
    unittest.main()
