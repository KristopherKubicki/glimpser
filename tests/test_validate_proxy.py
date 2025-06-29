import os
import unittest

from app.utils.validators import validate_proxy


class TestValidateProxy(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(validate_proxy(None))

    def test_blank(self):
        self.assertIsNone(validate_proxy("   "))

    def test_invalid_scheme(self):
        self.assertIsNone(validate_proxy("ftp://example.com"))

    def test_valid_http(self):
        self.assertEqual(validate_proxy("http://example.com"), "http://example.com")

    def test_valid_https(self):
        self.assertEqual(validate_proxy("https://example.com"), "https://example.com")

    def test_missing_netloc(self):
        self.assertIsNone(validate_proxy("http:///"))


if __name__ == "__main__":
    unittest.main()
