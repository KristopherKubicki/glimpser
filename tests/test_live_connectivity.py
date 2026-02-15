import unittest
from unittest.mock import patch

from app import routes


class TestLiveConnectivity(unittest.TestCase):
    @patch("app.routes.probe_url_with_range")
    def test_check_url_accessible_success(self, mock_probe):
        mock_probe.return_value = (True, {"ok": True})
        self.assertTrue(routes.check_url_accessible("http://example.com"))

    @patch("app.routes.probe_url_with_range", return_value=(False, {}))
    def test_check_url_accessible_failure(self, mock_probe):
        self.assertFalse(routes.check_url_accessible("http://bad"))


if __name__ == "__main__":
    unittest.main()
