"""Tests for auto update."""
import unittest
from unittest.mock import MagicMock, patch

from app.utils import auto_update


class TestAutoUpdate(unittest.TestCase):
    def test_ci_green(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"state": "success"}
        with patch("app.utils.auto_update.requests.get", return_value=resp):
            self.assertTrue(auto_update._ci_green("abc"))


if __name__ == "__main__":
    unittest.main()
