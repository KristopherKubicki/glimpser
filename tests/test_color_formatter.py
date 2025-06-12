import io
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.logging_utils import ColorFormatter


class TestColorFormatter(unittest.TestCase):
    def test_format_includes_ansi_codes(self):
        logger = logging.getLogger("color_test")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        formatter = ColorFormatter("%(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            logger.error("boom")
        finally:
            logger.removeHandler(handler)

        output = stream.getvalue().strip()
        self.assertIn("\033[", output)
        self.assertIn("boom", output)


if __name__ == "__main__":
    unittest.main()
