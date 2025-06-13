import json
import os
import unittest

from app.utils.template_manager import (
    LLM_COST_PER_TOKEN,
    LLM_USAGE_PATH,
    get_llm_cost_estimate,
    record_llm_usage,
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
        expected = round(2000 * LLM_COST_PER_TOKEN, 3)
        self.assertEqual(float(cost.strip("$")), expected)

    def test_cost_date_range(self):
        record_llm_usage("cam1", 1000)
        # rewrite timestamp of the first entry to an old date
        with open(LLM_USAGE_PATH, "r") as f:
            data = json.load(f)
        data["cam1"]["entries"][0]["time"] = "2000-01-01"
        with open(LLM_USAGE_PATH, "w") as f:
            json.dump(data, f)

        record_llm_usage("cam1", 500)
        cost = get_llm_cost_estimate("cam1", start_date="2020-01-01")
        expected = round(500 * LLM_COST_PER_TOKEN, 3)
        self.assertEqual(float(cost.strip("$")), expected)


if __name__ == "__main__":
    unittest.main()
