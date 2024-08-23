import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import (
    get_setting,
    DATABASE_PATH,
    UA,
    LANG,
    VERSION,
    NAME,
    HOST,
    PORT,
    DEBUG,
)


class TestConfig(unittest.TestCase):
    def test_database_path(self):
        self.assertTrue(os.path.exists(os.path.dirname(DATABASE_PATH)))

    @patch("app.config.SessionLocal")
    def test_get_setting_existing(self, mock_session):
        # Mock the database session and query result
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.execute.return_value.fetchone.return_value = [
            "test_value"
        ]

        result = get_setting("test_setting")
        self.assertEqual(result, "test_value")

    @patch("app.config.SessionLocal")
    def test_get_setting_non_existing(self, mock_session):
        # Mock the database session and query result for a non-existing setting
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.execute.return_value.fetchone.return_value = None

        result = get_setting("non_existing_setting", default="default_value")
        self.assertEqual(result, "default_value")

    @patch("app.config.SessionLocal")
    def test_get_setting_db_error(self, mock_session):
        # Mock the database session to raise an exception
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.execute.side_effect = Exception("Database error")

        result = get_setting("test_setting", default="default_value")
        self.assertEqual(result, "default_value")

    def test_config_values(self):
        self.assertIsInstance(UA, str)
        self.assertIsInstance(LANG, str)
        self.assertIsInstance(VERSION, float)
        self.assertIsInstance(NAME, str)
        self.assertIsInstance(HOST, str)
        self.assertIsInstance(PORT, int)
        self.assertIsInstance(DEBUG, bool)


if __name__ == "__main__":
    unittest.main()
