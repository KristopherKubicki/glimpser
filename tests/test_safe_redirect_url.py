import unittest

from app.routes import is_safe_redirect_url


class TestIsSafeRedirectUrl(unittest.TestCase):
    def test_valid_relative_urls(self):
        self.assertTrue(is_safe_redirect_url("/login"))
        self.assertTrue(is_safe_redirect_url("settings"))

    def test_invalid_urls(self):
        self.assertFalse(is_safe_redirect_url("http://example.com"))
        self.assertFalse(is_safe_redirect_url("https://site/path"))
        self.assertFalse(is_safe_redirect_url("/evil\n"))
        self.assertFalse(is_safe_redirect_url(None))
        self.assertFalse(is_safe_redirect_url("//host"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
