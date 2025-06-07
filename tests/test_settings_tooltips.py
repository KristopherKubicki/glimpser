import os
import sys
import unittest
import logging
import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import settings_tooltips as st
from app import config

# Silence warnings during import
logging.disable(logging.CRITICAL)


class TestSettingsTooltips(unittest.TestCase):
    def test_expected_keys_present(self):
        self.assertIn("API_KEY", st.SETTINGS_TOOLTIPS)
        self.assertIn("HOST", st.SETTINGS_CHOICES)
        self.assertIn("General", st.SETTINGS_GROUPS)

    def test_group_keys_defined(self):
        known = set(st.SETTINGS_TOOLTIPS) | set(st.SETTINGS_CHOICES)
        config_vars = {name for name, _ in inspect.getmembers(config) if name.isupper()}
        unknown = [
            key
            for names in st.SETTINGS_GROUPS.values()
            for key in names
            if key not in known
        ]
        missing = [key for key in unknown if key not in config_vars]
        self.assertEqual([], missing, f"Keys not defined in config: {missing}")

    def test_numeric_fields_subset(self):
        valid_keys = set(st.SETTINGS_TOOLTIPS) | set(
            key for names in st.SETTINGS_GROUPS.values() for key in names
        )
        self.assertTrue(set(st.NUMERIC_FIELDS).issubset(valid_keys))


if __name__ == "__main__":
    unittest.main()
