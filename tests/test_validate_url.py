import os
import unittest

from app.utils.validators import validate_url


class TestValidateURL(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(validate_url(None))

    def test_blank(self):
        self.assertIsNone(validate_url("   "))

    def test_invalid_scheme(self):
        self.assertIsNone(validate_url("ftp://example.com"))

    def test_dash_prefix(self):
        self.assertIsNone(validate_url("-http://example.com"))

    def test_newline(self):
        self.assertIsNone(validate_url("http://example.com/\nfoo"))

    def test_valid_http(self):
        self.assertEqual(validate_url("http://example.com"), "http://example.com")

    def test_valid_https_with_spaces(self):
        self.assertEqual(
            validate_url(" https://example.com "),
            "https://example.com",
        )


if __name__ == "__main__":
    unittest.main()
