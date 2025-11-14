import io
import logging
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

    def test_plain_handler_is_uncolored_with_colored_sibling(self):
        logger = logging.getLogger("color_test_plain")
        colored_stream = io.StringIO()
        plain_stream = io.StringIO()
        colored_handler = logging.StreamHandler(colored_stream)
        colored_handler.setFormatter(ColorFormatter("%(levelname)s:%(message)s"))
        plain_handler = logging.StreamHandler(plain_stream)
        plain_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
        logger.setLevel(logging.INFO)
        original_propagate = logger.propagate
        logger.propagate = False
        logger.addHandler(colored_handler)
        logger.addHandler(plain_handler)

        try:
            logger.warning("mixed output")
        finally:
            logger.removeHandler(colored_handler)
            logger.removeHandler(plain_handler)
            colored_handler.close()
            plain_handler.close()
            logger.propagate = original_propagate

        colored_output = colored_stream.getvalue().strip()
        plain_output = plain_stream.getvalue().strip()

        self.assertIn("\033[", colored_output)
        self.assertIn("mixed output", colored_output)
        self.assertNotIn("\033[", plain_output)
        self.assertIn("mixed output", plain_output)


if __name__ == "__main__":
    unittest.main()
