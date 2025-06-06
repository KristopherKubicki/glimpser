import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.validators import validate_setting


class TestValidateSetting(unittest.TestCase):
    def test_valid_port(self):
        self.assertEqual(validate_setting("PORT", "8080"), "8080")

    def test_invalid_port_range(self):
        self.assertIsNone(validate_setting("PORT", "80"))

    def test_invalid_port_type(self):
        self.assertIsNone(validate_setting("PORT", "abc"))

    def test_integer_setting(self):
        self.assertEqual(validate_setting("MAX_WORKERS", "4"), "4")
        self.assertIsNone(validate_setting("MAX_WORKERS", "bad"))

    def test_passthrough_unknown(self):
        self.assertEqual(validate_setting("CUSTOM", " value "), "value")


if __name__ == "__main__":
    unittest.main()
