# tests/test_init.py

import os
import unittest

from flask import Flask

from app import create_app


class TestCreateApp(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            enable_watchdog=False, schedule=False, log_cache=False
        )  # maybe?
        self.client = self.app.test_client()

    def test_app_creation(self):
        self.assertIsInstance(self.app, Flask)
        self.assertTrue(self.app.secret_key)

    def test_directory_creation(self):
        from app.config import (
            SCREENSHOT_DIRECTORY,
            SUMMARIES_DIRECTORY,
            VIDEO_DIRECTORY,
        )

        self.assertTrue(os.path.exists(SCREENSHOT_DIRECTORY))
        self.assertTrue(os.path.exists(VIDEO_DIRECTORY))
        self.assertTrue(os.path.exists(SUMMARIES_DIRECTORY))

    def test_routes_initialization(self):
        # Test if some expected routes are present
        with self.app.test_request_context():
            self.assertIn("index", self.app.view_functions)
            self.assertIn("login", self.app.view_functions)
            self.assertIn("logout", self.app.view_functions)

    """
    # wont work because schedule=False above
    def test_scheduler_initialization(self):
        scheduler = self.app.extensions.get("scheduler")
        self.assertIsInstance(scheduler, APScheduler)

    def test_scheduler_jobs(self):
        scheduler = self.app.extensions.get("scheduler")
        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        self.assertIn("compile_to_teaser", job_ids)
        self.assertIn("archive_screenshots", job_ids)
        self.assertIn("retention_cleanup", job_ids)
    """


if __name__ == "__main__":
    unittest.main()
