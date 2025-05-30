import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.template_manager import get_llm_response_count


class TestLLMResponseCount(unittest.TestCase):
    @patch("app.utils.template_manager.random.randint", return_value=42)
    def test_get_llm_response_count(self, mock_randint):
        """get_llm_response_count should return the patched random value."""
        result = get_llm_response_count("cam1")
        self.assertEqual(result, 42)
        mock_randint.assert_called_once_with(10, 100)


if __name__ == "__main__":
    unittest.main()
