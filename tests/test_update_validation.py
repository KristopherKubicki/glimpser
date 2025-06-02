import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.validators import validate_update_data


class TestValidateUpdateData(unittest.TestCase):
    def test_defaults_and_ranges(self):
        data = {
            "url": "http://example",
            "frequency": "0",
            "timeout": "100000",
            "object_confidence": "2",
            "motion": "-1",
            "rollback_frames": "-5",
        }
        result = validate_update_data(data)
        self.assertEqual(result["frequency"], 1)
        self.assertLess(result["timeout"], result["frequency"] * 60)
        self.assertEqual(result["object_confidence"], 1.0)
        self.assertEqual(result["motion"], 0.0)
        self.assertEqual(result["rollback_frames"], 0)

    def test_missing_url_raises(self):
        with self.assertRaises(ValueError):
            validate_update_data({})

    def test_invalid_proxy_removed(self):
        data = {"url": "http://example", "proxy": "   "}
        result = validate_update_data(data)
        self.assertNotIn("proxy", result)

    def test_valid_proxy_preserved(self):
        data = {"url": "http://example", "proxy": "http://localhost:8080"}
        result = validate_update_data(data)
        self.assertEqual(result["proxy"], "http://localhost:8080")

    def test_stealth_defaults(self):
        data = {"url": "http://example", "stealth": True}
        result = validate_update_data(data)
        self.assertEqual(result["frequency"], 60)
        self.assertEqual(result["timeout"], 30)

    def test_browser_defaults(self):
        data = {"url": "http://example", "browser": True}
        result = validate_update_data(data)
        self.assertEqual(result["frequency"], 60)
        self.assertEqual(result["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
