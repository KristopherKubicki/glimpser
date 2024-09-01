import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main
import app.config as config


class TestMain(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.old_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = os.path.join(self.temp_dir, "test.db")

    def tearDown(self):
        config.DATABASE_PATH = self.old_db_path
        # Clean up the temporary directory
        if os.path.exists(self.temp_dir):
            for root, dirs, files in os.walk(self.temp_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(self.temp_dir)

    def test_parse_arguments(self):
        with patch(
            "sys.argv", ["main.py", "--db-path", os.path.join(self.temp_dir, "db.sqlite"), "--port", "8080"]
        ):
            args = main.parse_arguments()
            self.assertEqual(args.db_path, os.path.join(self.temp_dir, "db.sqlite"))
            self.assertEqual(args.port, 8080)

    def test_setup_config(self):
        args = MagicMock()
        args.db_path = os.path.join(self.temp_dir, "db.sqlite")
        args.host = "localhost"
        args.port = 8080
        args.log_path = os.path.join(self.temp_dir, "log.txt")
        args.debug = True
        args.screenshot_dir = os.path.join(self.temp_dir, "screenshots")
        args.video_dir = os.path.join(self.temp_dir, "videos")
        args.summaries_dir = os.path.join(self.temp_dir, "summaries")

        main.setup_config(args)

        self.assertEqual(config.DATABASE_PATH, os.path.join(self.temp_dir, "db.sqlite"))
        self.assertEqual(config.HOST, "localhost")
        self.assertEqual(config.PORT, 8080)
        self.assertEqual(config.LOGGING_PATH, os.path.join(self.temp_dir, "log.txt"))
        self.assertTrue(config.DEBUG_MODE)
        self.assertEqual(config.SCREENSHOT_DIRECTORY, os.path.join(self.temp_dir, "screenshots"))
        self.assertEqual(config.VIDEO_DIRECTORY, os.path.join(self.temp_dir, "videos"))
        self.assertEqual(config.SUMMARIES_DIRECTORY, os.path.join(self.temp_dir, "summaries"))

    @patch.object(logging, 'getLogger')
    def test_setup_logging(self, mock_get_logger):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        args = MagicMock()
        args.log_level = "DEBUG"
        args.console_log = True

        main.setup_logging(args)

        mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
        #mock_logger.addHandler.assert_any_call(mock.ANY)  # Check that any handler was added
 
    '''
    @patch("logging.FileHandler")
    @patch("logging.StreamHandler")
    def test_setup_logging(self, mock_stream_handler, mock_file_handler):
        args = MagicMock()
        args.log_level = "DEBUG"
        args.console_log = True

        main.setup_logging(args)

        mock_file_handler.assert_called_once()
        mock_stream_handler.assert_called_once()
    '''

    @patch("os.makedirs")
    def test_ensure_directories(self, mock_makedirs):
        main.ensure_directories()
        self.assertEqual(mock_makedirs.call_count, 5)

    @patch("generate_credentials.generate_credentials")
    @patch("os.path.exists")
    def test_generate_credentials_if_needed(self, mock_exists, mock_generate):
        mock_exists.return_value = False
        main.generate_credentials_if_needed()
        mock_generate.assert_called_once()

        mock_exists.return_value = True
        main.generate_credentials_if_needed()
        mock_generate.assert_called_once()  # Still only called once

    @patch("main.create_app")
    @patch("main.ensure_directories")
    @patch("main.generate_credentials_if_needed")
    def test_create_application(self, mock_generate, mock_ensure, mock_create_app):
        result = main.create_application()
        mock_ensure.assert_called_once()
        mock_generate.assert_called_once()
        mock_create_app.assert_called_once()
        self.assertEqual(result, mock_create_app.return_value)


if __name__ == "__main__":
    unittest.main()
