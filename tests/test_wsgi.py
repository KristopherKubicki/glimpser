"""Tests for wsgi."""
import importlib
import unittest
from unittest.mock import patch


class TestWSGI(unittest.TestCase):
    def test_app_created_on_import(self):
        with patch("main.create_application", return_value="sentinel") as mock_create:
            import sys

            sys.modules.pop("wsgi", None)
            module = importlib.import_module("wsgi")
            self.assertEqual(module.app, "sentinel")
            mock_create.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
