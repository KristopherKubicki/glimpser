import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.scheduling import (
    update_camera,
    init_crawl,
    update_summary,
    schedule_summarization,
    schedule_crawlers,
)


class TestScheduling(unittest.TestCase):
    @patch("app.utils.scheduling.get_template")
    @patch("app.utils.scheduling.capture_or_download")
    @patch("app.utils.scheduling.add_timestamp")
    @patch("app.utils.scheduling.os.path.exists")
    @patch("app.utils.scheduling.os.rename")
    def test_update_camera(
        self,
        mock_rename,
        mock_exists,
        mock_add_timestamp,
        mock_capture,
        mock_get_template,
    ):
        # Setup
        mock_get_template.return_value = {"name": "test_camera", "frequency": 30}
        mock_capture.return_value = True
        mock_exists.return_value = True

        # Call the function
        update_camera("test_camera", {})

        # Assertions
        mock_get_template.assert_called_once_with("test_camera")
        mock_capture.assert_called_once()
        mock_add_timestamp.assert_called_once()
        mock_rename.assert_called()

    @patch("app.utils.scheduling.get_templates")
    @patch("app.utils.scheduling.update_camera")
    def test_init_crawl(self, mock_update_camera, mock_get_templates):
        # Setup
        mock_get_templates.return_value = {"camera1": {}, "camera2": {}}

        # Call the function
        init_crawl()

        # Assertions
        mock_get_templates.assert_called_once()
        self.assertEqual(mock_update_camera.call_count, 2)

    @patch("app.utils.scheduling.get_templates")
    @patch("app.utils.scheduling.summarize")
    def test_update_summary(self, mock_summarize, mock_get_templates):
        # Setup
        mock_get_templates.return_value = {
            "camera1": {"name": "Camera 1", "last_caption_time": "2023-06-01 12:00:00"},
            "camera2": {"name": "Camera 2", "last_caption_time": "2023-06-01 13:00:00"},
        }
        mock_summarize.return_value = "Summary text"

        # Call the function
        update_summary()

        # Assertions
        mock_get_templates.assert_called_once()
        mock_summarize.assert_called_once()

    @patch("app.utils.scheduling.scheduler")
    def test_schedule_summarization(self, mock_scheduler):
        # Call the function
        schedule_summarization()

        # Assertions
        mock_scheduler.add_job.assert_called_once()

    @patch("app.utils.scheduling.get_templates")
    @patch("app.utils.scheduling.scheduler")
    @patch("app.utils.scheduling.os.makedirs")
    def test_schedule_crawlers(self, mock_makedirs, mock_scheduler, mock_get_templates):
        # Setup
        mock_get_templates.return_value = {
            "camera1": {"name": "Camera 1", "frequency": 30},
            "camera2": {"name": "Camera 2", "frequency": 60},
        }

        # Call the function
        schedule_crawlers()

        # Assertions
        mock_get_templates.assert_called_once()
        self.assertEqual(
            mock_scheduler.add_job.call_count, 3
        )  # 2 for cameras, 1 for init_crawl
        self.assertEqual(
            mock_makedirs.call_count, 4
        )  # 2 for each camera (screenshot and video directories)


if __name__ == "__main__":
    unittest.main()
