import json
import os
import tempfile
import unittest
from unittest.mock import patch

import app.utils.template_manager as template_manager


class TestLLMCostSummary(unittest.TestCase):
    def setUp(self):
        # Isolate usage file per test instance to avoid xdist parallel clobbering.
        self._tmpdir = tempfile.TemporaryDirectory()
        template_manager.LLM_USAGE_PATH = os.path.join(
            self._tmpdir.name, "llm_usage.json"
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_summary_totals(self):
        with open(template_manager.LLM_USAGE_PATH, "w") as f:
            json.dump({"cam1": 500, "cam2": 1500}, f)
        summary, tokens, cost, calls = template_manager.get_llm_cost_summary()
        self.assertEqual(tokens, 2000)
        expected_cost = round(2000 * template_manager.LLM_COST_PER_TOKEN, 3)
        self.assertEqual(cost, f"${expected_cost:.3f}")
        self.assertEqual(len(summary), 2)
        self.assertEqual(calls, 2)

    def test_group_cost_summary(self):
        summary = [
            {
                "name": f"cam{i}",
                "tokens": i,
                "cost": f"${i:.3f}",
                "calls": 1,
            }
            for i in range(1, 12)
        ]
        grouped = template_manager.group_cost_summary(summary, top=10)
        self.assertEqual(len(grouped), 10)
        self.assertEqual(grouped[-1]["name"], "Other")

    @patch("app.utils.template_manager.TemplateManager.get_templates")
    def test_summary_filtered_by_group(self, mock_get_templates):
        mock_get_templates.return_value = {
            "cam1": {"groups": "a"},
            "cam2": {"groups": "b"},
        }
        with open(template_manager.LLM_USAGE_PATH, "w") as f:
            json.dump({"cam1": 100, "cam2": 200}, f)
        summary, tokens, cost, calls = template_manager.get_llm_cost_summary(group="a")
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["name"], "cam1")


if __name__ == "__main__":
    unittest.main()
