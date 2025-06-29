"""Tests for installation and first use."""
import os
import shutil
import tempfile
import unittest
from importlib import reload

from flask import Flask

import app.config as config
from app import create_app
from app.utils import db
from app.utils.template_manager import TemplateManager

# Add the parent directory to the Python path


class TestInstallationAndFirstUse(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()

        # Set up temporary paths for testing
        self.original_db_path = config.DATABASE_PATH
        self.original_screenshot_dir = config.SCREENSHOT_DIRECTORY
        self.original_video_dir = config.VIDEO_DIRECTORY
        self.original_summaries_dir = config.SUMMARIES_DIRECTORY

        config.DATABASE_PATH = os.path.join(self.temp_dir, "test_glimpser.db")
        config.SCREENSHOT_DIRECTORY = os.path.join(self.temp_dir, "screenshots")
        config.VIDEO_DIRECTORY = os.path.join(self.temp_dir, "video")
        config.SUMMARIES_DIRECTORY = os.path.join(self.temp_dir, "summaries")

        # Create the Flask test client
        self.app = create_app(enable_watchdog=False, schedule=False, log_cache=False)
        self.client = self.app.test_client()

    def tearDown(self):
        # Restore original paths
        config.DATABASE_PATH = self.original_db_path
        config.SCREENSHOT_DIRECTORY = self.original_screenshot_dir
        config.VIDEO_DIRECTORY = self.original_video_dir
        config.SUMMARIES_DIRECTORY = self.original_summaries_dir

        # Remove the temporary directory and its contents
        shutil.rmtree(self.temp_dir)

    def test_app_creation(self):
        """Test that the app is created successfully"""
        self.assertIsNotNone(self.app)
        self.assertTrue(isinstance(self.app, Flask))

    def test_directory_creation(self):
        """Test that required directories are created"""
        self.assertTrue(os.path.exists(config.SCREENSHOT_DIRECTORY))
        self.assertTrue(os.path.exists(config.VIDEO_DIRECTORY))
        self.assertTrue(os.path.exists(config.SUMMARIES_DIRECTORY))

    def test_database_initialization(self):
        """Test that the database file is created"""
        reload(db)
        TemplateManager()
        self.assertTrue(os.path.exists(config.DATABASE_PATH))

    def test_root_route(self):
        """Test the root route of the application"""
        response = self.client.get("/")
        self.assertEqual(
            response.status_code, 302
        )  # will be a redirect because of no auth
        self.assertTrue("/login" in response.text)


if __name__ == "__main__":
    unittest.main()
