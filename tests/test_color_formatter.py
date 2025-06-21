import io
import logging
import os
import unittest

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
