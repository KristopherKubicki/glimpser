import os
import json
import unittest
from app.utils.template_manager import (
    record_llm_usage,
    get_llm_cost_estimate,
    LLM_USAGE_PATH,
    LLM_COST_PER_TOKEN,
)


class TestLLMCostTracking(unittest.TestCase):
    def setUp(self):
        if os.path.exists(LLM_USAGE_PATH):
            os.remove(LLM_USAGE_PATH)

    def tearDown(self):
        if os.path.exists(LLM_USAGE_PATH):
            os.remove(LLM_USAGE_PATH)

    def test_record_and_get_cost(self):
        record_llm_usage("cam1", 2000)
        cost = get_llm_cost_estimate("cam1")
        expected = 2000 * LLM_COST_PER_TOKEN
        self.assertAlmostEqual(float(cost.strip("$")), expected, places=2)


if __name__ == "__main__":
    unittest.main()
