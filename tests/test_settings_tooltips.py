import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.settings_tooltips import (
    SETTINGS_TOOLTIPS,
    SETTINGS_CHOICES,
    SETTINGS_GROUPS,
)


class TestSettingsTooltips(unittest.TestCase):
    def test_common_keys_exist(self):
        """Ensure there are some keys common to all dicts."""
        tooltips_keys = set(SETTINGS_TOOLTIPS.keys())
        choices_keys = set(SETTINGS_CHOICES.keys())
        groups_keys = {k for lst in SETTINGS_GROUPS.values() for k in lst}
        common = tooltips_keys & choices_keys & groups_keys
        self.assertTrue(common)
        self.assertIn("LOG_LEVEL", common)

    def test_group_values_unique(self):
        """Check that each setting appears only once across SETTINGS_GROUPS."""
        all_values = [val for group in SETTINGS_GROUPS.values() for val in group]
        duplicates = {v for v in all_values if all_values.count(v) > 1}
        self.assertFalse(duplicates, msg=f"Duplicate group values found: {duplicates}")

    def test_choices_and_groups_in_tooltips(self):
        """Any key in choices or groups must exist in tooltips."""
        tooltip_keys = set(SETTINGS_TOOLTIPS.keys())
        choice_keys = set(SETTINGS_CHOICES.keys())
        group_keys = {k for lst in SETTINGS_GROUPS.values() for k in lst}
        missing = (choice_keys | group_keys) - tooltip_keys
        self.assertFalse(missing, msg=f"Missing keys in tooltips: {missing}")


if __name__ == "__main__":
    unittest.main()
