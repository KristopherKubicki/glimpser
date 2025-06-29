"""Tests for sanitize url."""
import unittest
from unittest.mock import patch

from app.utils.logging_utils import sanitize_url


class TestSanitizeUrl(unittest.TestCase):
    def test_logs_on_parse_error(self):
        with patch("app.utils.logging_utils.urlparse", side_effect=ValueError("boom")):
            with self.assertLogs("app.utils.logging_utils", level="DEBUG") as logs:
                result = sanitize_url("http://user:pass@example.com")
        self.assertEqual(result, "http://user:pass@example.com")
        joined = "\n".join(logs.output)
        self.assertIn("boom", joined)


if __name__ == "__main__":
    unittest.main()
