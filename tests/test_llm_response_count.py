import json
import os
import unittest

from app.utils.template_manager import LLM_USAGE_PATH, get_llm_response_count


class TestLLMResponseCount(unittest.TestCase):
    def setUp(self):
        if os.path.exists(LLM_USAGE_PATH):
            os.remove(LLM_USAGE_PATH)

    def tearDown(self):
        if os.path.exists(LLM_USAGE_PATH):
            os.remove(LLM_USAGE_PATH)

    def test_get_llm_response_count(self):
        """Counts the number of stored responses for the template."""
        os.makedirs(os.path.dirname(LLM_USAGE_PATH), exist_ok=True)
        with open(LLM_USAGE_PATH, "w") as f:
            json.dump({"cam1": [1, 2, 3]}, f)

        result = get_llm_response_count("cam1")
        self.assertEqual(result, 3)


if __name__ == "__main__":
    unittest.main()
