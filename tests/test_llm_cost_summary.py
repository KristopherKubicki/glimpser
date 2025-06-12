import json
import os
import unittest

from app.utils.template_manager import (
    LLM_COST_PER_TOKEN,
    LLM_USAGE_PATH,
    get_llm_cost_summary,
    group_cost_summary,
)


class TestLLMCostSummary(unittest.TestCase):
    def setUp(self):
        if os.path.exists(LLM_USAGE_PATH):
            os.remove(LLM_USAGE_PATH)

    def tearDown(self):
        if os.path.exists(LLM_USAGE_PATH):
            os.remove(LLM_USAGE_PATH)

    def test_summary_totals(self):
        with open(LLM_USAGE_PATH, "w") as f:
            json.dump({"cam1": 500, "cam2": 1500}, f)
        summary, tokens, cost = get_llm_cost_summary()
        self.assertEqual(tokens, 2000)
        expected_cost = round(2000 * LLM_COST_PER_TOKEN, 3)
        self.assertEqual(cost, f"${expected_cost:.3f}")
        self.assertEqual(len(summary), 2)

    def test_group_cost_summary(self):
        summary = [
            {"name": f"cam{i}", "tokens": i, "cost": f"${i:.3f}"} for i in range(1, 12)
        ]
        grouped = group_cost_summary(summary, top=10)
        self.assertEqual(len(grouped), 10)
        self.assertEqual(grouped[-1]["name"], "Other")


if __name__ == "__main__":
    unittest.main()
