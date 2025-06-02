import unittest
import os
import sys
from unittest.mock import patch

from PIL import ImageFont

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.utils.screenshots as ss


class TestScreenshotsMisc(unittest.TestCase):
    def test_random_user_agent(self):
        template = ss.STEALTH_UA_TEMPLATES[0]
        with (
            patch(
                "app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome"
            ),
            patch("app.utils.screenshots.get_chrome_version", return_value=120),
            patch("app.utils.screenshots.random.choice", return_value=template),
            patch("app.utils.screenshots.random.randint", return_value=121),
        ):
            ua = ss.random_user_agent()
        self.assertEqual(ua, template.format(version=121))

    def test_load_font_fallback(self):
        original_load_default = ImageFont.load_default

        class DummyImageFont:
            @staticmethod
            def truetype(*args, **kwargs):
                raise IOError

            @staticmethod
            def load_default():
                return original_load_default()

        with patch("app.utils.screenshots.ImageFont", DummyImageFont):
            font = ss.load_font(12)

        self.assertEqual(font.getname(), ImageFont.load_default().getname())


if __name__ == "__main__":
    unittest.main()
