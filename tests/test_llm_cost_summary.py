import os
import json
import unittest
from app.utils.template_manager import (
    get_llm_cost_summary,
    LLM_USAGE_PATH,
    LLM_COST_PER_TOKEN,
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


if __name__ == "__main__":
    unittest.main()
