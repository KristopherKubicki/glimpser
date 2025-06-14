import unittest
from unittest.mock import patch

import app.routes as routes


class TestLiveConnectivity(unittest.TestCase):
    @patch("app.routes.requests.head")
    def test_check_url_accessible_success(self, mock_head):
        mock_head.return_value.ok = True
        self.assertTrue(routes.check_url_accessible("http://example.com"))

    @patch("app.routes.requests.head", side_effect=Exception("fail"))
    def test_check_url_accessible_failure(self, mock_head):
        self.assertFalse(routes.check_url_accessible("http://bad"))


if __name__ == "__main__":
    unittest.main()
