import json
import os
import tempfile
import unittest

import app.utils.template_manager as template_manager


class TestLLMResponseCount(unittest.TestCase):
    def setUp(self):
        # Isolate usage file per test instance to avoid xdist parallel clobbering.
        self._tmpdir = tempfile.TemporaryDirectory()
        template_manager.LLM_USAGE_PATH = os.path.join(
            self._tmpdir.name, "llm_usage.json"
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_llm_response_count(self):
        """Counts the number of stored responses for the template."""
        os.makedirs(os.path.dirname(template_manager.LLM_USAGE_PATH), exist_ok=True)
        with open(template_manager.LLM_USAGE_PATH, "w") as f:
            json.dump({"cam1": [1, 2, 3]}, f)

        result = template_manager.get_llm_response_count("cam1")
        self.assertEqual(result, 3)


if __name__ == "__main__":
    unittest.main()
