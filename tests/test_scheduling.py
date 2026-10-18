# test/test_scheduling.py

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from PIL import Image

from app.utils.scheduling import (
    _caption_refresh_due,
    _caption_refresh_hours,
    find_closest_image,
    scheduler,
    start_log_caching,
)


class TestScheduler(unittest.TestCase):
    @patch("time.sleep", return_value=None)  # Corrected patch target
    def test_schedule_job(self, mock_sleep):
        job = MagicMock()

        try:
            scheduler.remove_job("test_job")
        except Exception:
            pass
        # Schedule a job using add_job with correct argument passing
        scheduler.add_job(func=job, trigger="interval", seconds=5, id="test_job")

        # Simulate the running of the scheduler (normally done in a separate thread)
        job_func = scheduler.get_job("test_job").func
        job_func()  # hopefully takes less than 5 seconds

        job.assert_called_once()
        scheduler.remove_job("test_job")

    @patch("time.sleep", return_value=None)  # Corrected patch target
    def test_run_scheduled_jobs(self, mock_sleep):
        job1 = MagicMock()
        job2 = MagicMock()

        # Schedule the jobs using add_job with correct argument passing
        scheduler.add_job(func=job1, trigger="interval", seconds=1, id="test_job1")
        scheduler.add_job(func=job2, trigger="interval", seconds=1, id="test_job2")

        # Simulate the running of the scheduler (normally done in a separate thread)
        job_func1 = scheduler.get_job("test_job1").func
        job_func2 = scheduler.get_job("test_job2").func
        job_func1()
        job_func2()

        job1.assert_called_once()
        job2.assert_called_once()
        scheduler.remove_job("test_job1")
        scheduler.remove_job("test_job2")

    @patch("time.sleep", return_value=None)  # Corrected patch target
    def test_scheduler_continues_after_exception(self, mock_sleep):
        job1 = MagicMock(side_effect=Exception("Test Exception"))
        job2 = MagicMock()

        try:
            scheduler.remove_job("test_job1")
        except Exception:
            pass
        try:
            scheduler.remove_job("test_job2")
        except Exception:
            pass

        # Schedule the jobs using add_job with correct argument passing
        scheduler.add_job(func=job1, trigger="interval", seconds=1, id="test_job1")
        scheduler.add_job(func=job2, trigger="interval", seconds=1, id="test_job2")

        # Manually invoke job_func1 to raise the exception
        job_func1 = scheduler.get_job("test_job1").func

        # Simulate job execution, with job1 raising an exception
        try:
            job_func1()
        except Exception as e:
            self.assertEqual(str(e), "Test Exception")
            job1.assert_called_once()

        # Ensure job2 still runs
        job_func2 = scheduler.get_job("test_job2").func
        job_func2()
        job2.assert_called_once()
        scheduler.remove_job("test_job2")

    @patch("time.sleep", return_value=None)
    def test_remove_scheduled_job(self, mock_sleep):
        job = MagicMock()

        # Schedule a job
        try:
            scheduler.remove_job("test_job")
        except Exception:
            pass
        scheduler.add_job(func=job, trigger="interval", seconds=5, id="test_job")

        # Verify the job is scheduled
        self.assertIsNotNone(scheduler.get_job("test_job"))

        # Remove the job
        scheduler.remove_job("test_job")

        # Verify the job is removed
        self.assertIsNone(scheduler.get_job("test_job"))

    @patch("threading.Thread")
    @patch("app.utils.scheduling.scheduler.add_job")
    def test_start_log_caching_only_spawns_thread(self, mock_add_job, mock_thread):
        mock_thread.return_value.start = MagicMock()

        start_log_caching()

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        mock_add_job.assert_not_called()

    def test_find_closest_image_none_when_outside_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            times = [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 0, 5, 0),
            ]
            for t in times:
                filename = t.strftime("%Y%m%d%H%M%S") + "_motion.png"
                Image.new("RGB", (1, 1)).save(os.path.join(tmp, filename))

            last_caption_time = datetime(2023, 1, 1, 0, 10, 0)
            result = find_closest_image(
                tmp, last_caption_time, max_time_diff=timedelta(seconds=60)
            )
            self.assertIsNone(result)

    def test_caption_refresh_hours_by_frequency(self):
        self.assertEqual(_caption_refresh_hours({"frequency": 60}), 24.0)
        self.assertEqual(_caption_refresh_hours({"frequency": 30}), 8.0)
        self.assertEqual(_caption_refresh_hours({"frequency": 5}), 3.0)
        self.assertEqual(
            _caption_refresh_hours({"frequency": 14, "livecaption": True}), 2.0
        )

    def test_caption_refresh_due_ignores_motion_allow_state(self):
        now = datetime(2026, 5, 4, 12, 0, 0)
        stale_static_camera = {
            "frequency": 30,
            "last_caption": "Existing caption",
            "last_caption_time": "2026-05-04 03:30:00",
            "last_motion_caption": "",
        }
        fresh_static_camera = {
            **stale_static_camera,
            "last_caption_time": "2026-05-04 05:00:00",
        }

        self.assertTrue(_caption_refresh_due(stale_static_camera, now=now))
        self.assertFalse(_caption_refresh_due(fresh_static_camera, now=now))

    def test_caption_refresh_due_when_timestamp_missing_or_invalid(self):
        self.assertTrue(_caption_refresh_due({"last_caption": ""}))
        self.assertTrue(
            _caption_refresh_due(
                {"last_caption": "Existing caption", "last_caption_time": ""}
            )
        )
        self.assertTrue(
            _caption_refresh_due(
                {
                    "last_caption": "Existing caption",
                    "last_caption_time": "not a timestamp",
                }
            )
        )

    """
    @patch('app.utils.scheduling.scheduler.add_job')
    @patch('app.utils.scheduling.get_templates', return_value={
        'camera1': {'name': 'camera1', 'frequency': 30},
        'camera2': {'name': 'camera2', 'frequency': 60},
    })
    def test_schedule_crawlers(self, mock_get_templates, mock_add_job):
        schedule_crawlers()
        # Ensure that jobs are being scheduled
        self.assertEqual(mock_add_job.call_count, 2)

    @patch('app.utils.scheduling.scheduler.add_job')
    def test_schedule_crawlers_empty_templates(self, mock_add_job):
        with patch('app.utils.scheduling.get_templates', return_value={}):
            schedule_crawlers()
            # Ensure no jobs are scheduled when templates are empty
            mock_add_job.assert_not_called()

    def test_calculate_optimal_offsets_unique(self):
        templates = {
            'a': {'name': 'a', 'frequency': 30},
            'b': {'name': 'b', 'frequency': 30},
            'c': {'name': 'c', 'frequency': 60},
        }
        offsets = scheduling.calculate_optimal_offsets(templates, 10)
        self.assertEqual(len(set(offsets.values())), len(templates))
    """


if __name__ == "__main__":
    unittest.main()
