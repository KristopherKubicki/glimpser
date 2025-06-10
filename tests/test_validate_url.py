import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.validators import validate_url


class TestValidateUrl(unittest.TestCase):
    def test_valid_http(self):
        self.assertEqual(validate_url("http://example.com"), "http://example.com")

    def test_valid_https(self):
        self.assertEqual(validate_url("https://example.com"), "https://example.com")

    def test_invalid_scheme(self):
        self.assertIsNone(validate_url("ftp://example.com"))

    def test_disallows_newline_and_dash(self):
        self.assertIsNone(validate_url("http://example.com\n"))
        self.assertIsNone(validate_url("-http://bad"))

    def test_none_returns_none(self):
        self.assertIsNone(validate_url(None))


if __name__ == "__main__":
    unittest.main()
