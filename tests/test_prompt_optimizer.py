import os
import unittest
from unittest.mock import patch

import app.utils.image_processing as img_proc  # noqa: E402
from app.utils import prompt_optimizer  # noqa: E402


class TestPromptOptimizer(unittest.TestCase):
    @patch("app.utils.prompt_optimizer.ChatGPTImageComparison.compare_images")
    @patch("pathlib.Path.exists")
    @patch("app.utils.prompt_optimizer.get_screenshots_for_template")
    @patch("app.utils.prompt_optimizer.CHATGPT_KEY", "k")
    def test_generate_prompt_returns_caption(self, mock_get, mock_exists, mock_compare):
        mock_get.return_value = ["shot1.png", "shot2.png"]
        mock_exists.return_value = True
        mock_compare.return_value = ("Caption here", 10)

        original = img_proc.LLM_CAPTION_PROMPT
        result = prompt_optimizer.generate_prompt("cam1")

        self.assertEqual(result, "Caption here")
        self.assertEqual(img_proc.LLM_CAPTION_PROMPT, original)
        mock_compare.assert_called_once()

    @patch("app.utils.prompt_optimizer.ChatGPTImageComparison.compare_images")
    @patch("pathlib.Path.exists")
    @patch("app.utils.prompt_optimizer.get_screenshots_for_template")
    @patch("app.utils.prompt_optimizer.CHATGPT_KEY", "k")
    def test_generate_prompt_no_images(self, mock_get, mock_exists, mock_compare):
        mock_get.return_value = ["shot1.png"]
        mock_exists.return_value = False

        original = img_proc.LLM_CAPTION_PROMPT
        result = prompt_optimizer.generate_prompt("cam1")

        self.assertEqual(result, "")
        self.assertEqual(img_proc.LLM_CAPTION_PROMPT, original)
        mock_compare.assert_not_called()

    @patch("app.utils.prompt_optimizer.ChatGPTImageComparison.compare_images")
    @patch("pathlib.Path.exists")
    @patch("app.utils.prompt_optimizer.get_screenshots_for_template")
    @patch("app.utils.prompt_optimizer.CHATGPT_KEY", "")
    def test_generate_prompt_no_key(self, mock_get, mock_exists, mock_compare):
        mock_get.return_value = ["shot1.png"]
        mock_exists.return_value = True

        original = img_proc.LLM_CAPTION_PROMPT
        result = prompt_optimizer.generate_prompt("cam1")

        self.assertEqual(result, "")
        self.assertEqual(img_proc.LLM_CAPTION_PROMPT, original)
        mock_compare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
