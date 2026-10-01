import unittest

from app import config
from app.utils.settings_tooltips import SETTINGS_CHOICES, SETTINGS_TOOLTIPS


class TestSettingsTooltips(unittest.TestCase):
    def test_required_keys_present(self):
        self.assertIn("API_KEY", SETTINGS_TOOLTIPS)
        self.assertIn("CHATGPT_KEY", SETTINGS_TOOLTIPS)
        self.assertIn("NOTIFY_ON_MOTION", SETTINGS_TOOLTIPS)
        self.assertIn("NOTIFY_ON_CAPTION", SETTINGS_TOOLTIPS)
        self.assertIn("LOW_CPU_MODE", SETTINGS_TOOLTIPS)

    def test_choices_have_tooltip_or_default(self):
        for key in SETTINGS_CHOICES:
            with self.subTest(key=key):
                self.assertTrue(
                    key in SETTINGS_TOOLTIPS or hasattr(config, key),
                    f"Missing tooltip and default for {key}",
                )


if __name__ == "__main__":
    unittest.main()
