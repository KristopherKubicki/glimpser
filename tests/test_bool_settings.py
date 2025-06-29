import os
import unittest
from unittest.mock import patch

from app.routes import get_all_settings
from app.utils.validators import BOOLEAN_SETTINGS, is_bool_string


class DummySession:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query):
        class Result:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        return Result(self.rows)

    def close(self):
        pass


class TestBoolHelpers(unittest.TestCase):
    def test_is_bool_string(self):
        for val in ["True", "false", "YES", "off", "Y", "n", "t", "f"]:
            self.assertTrue(is_bool_string(val))
        for val in ["maybe", "1", ""]:
            self.assertFalse(is_bool_string(val))

    @patch("app.routes.SessionLocal")
    def test_get_all_settings_normalizes(self, mock_session):
        mock_session.return_value = DummySession([("MYFLAG", "yes")])
        with patch("app.routes.SENSITIVE_SETTINGS", []):
            settings = get_all_settings()
        found = next((s for s in settings if s["name"] == "MYFLAG"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "True")

    def test_new_settings_in_boolean_list(self):
        self.assertIn("NOTIFY_ON_MOTION", BOOLEAN_SETTINGS)
        self.assertIn("NOTIFY_ON_CAPTION", BOOLEAN_SETTINGS)


if __name__ == "__main__":
    unittest.main()
