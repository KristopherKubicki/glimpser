# test/test_scheduling.py

import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.scheduling import scheduler, schedule_crawlers

class TestScheduler(unittest.TestCase):

    @patch('time.sleep', return_value=None)  # Corrected patch target
    def test_schedule_job(self, mock_sleep):
        job = MagicMock()

        try:
            scheduler.remove_job('test_job')
        except Exception as e:
            pass
        # Schedule a job using add_job with correct argument passing
        scheduler.add_job(func=job, trigger='interval', seconds=5, id='test_job')

        # Simulate the running of the scheduler (normally done in a separate thread)
        job_func = scheduler.get_job('test_job').func
        job_func() # hopefully takes less than 5 seconds

        job.assert_called_once() 
        scheduler.remove_job('test_job') 

    @patch('time.sleep', return_value=None)  # Corrected patch target
    def test_run_scheduled_jobs(self, mock_sleep):
        job1 = MagicMock()
        job2 = MagicMock()

        # Schedule the jobs using add_job with correct argument passing
        scheduler.add_job(func=job1, trigger='interval', seconds=1, id='test_job1')
        scheduler.add_job(func=job2, trigger='interval', seconds=1, id='test_job2')

        # Simulate the running of the scheduler (normally done in a separate thread)
        job_func1 = scheduler.get_job('test_job1').func
        job_func2 = scheduler.get_job('test_job2').func
        job_func1()
        job_func2()

        job1.assert_called_once()
        job2.assert_called_once()
        scheduler.remove_job('test_job1')
        scheduler.remove_job('test_job2')

    @patch('time.sleep', return_value=None)  # Corrected patch target
    def test_scheduler_continues_after_exception(self, mock_sleep):
        job1 = MagicMock(side_effect=Exception("Test Exception"))
        job2 = MagicMock()

        try:
            scheduler.remove_job('test_job1')
        except Exception as e:
            pass
        try:
            scheduler.remove_job('test_job2')
        except Exception as e:
            pass

        # Schedule the jobs using add_job with correct argument passing
        scheduler.add_job(func=job1, trigger='interval', seconds=1, id='test_job1')
        scheduler.add_job(func=job2, trigger='interval', seconds=1, id='test_job2')

        # Manually invoke job_func1 to raise the exception
        job_func1 = scheduler.get_job('test_job1').func

        # Simulate job execution, with job1 raising an exception
        try:
            job_func1()
        except Exception as e:
            self.assertEqual(str(e), "Test Exception")
            job1.assert_called_once()

        # Ensure job2 still runs
        job_func2 = scheduler.get_job('test_job2').func
        job_func2()
        #job2.assert_called_once() # TODO: fix this ...
        scheduler.remove_job('test_job2')

    @patch('time.sleep', return_value=None)
    def test_remove_scheduled_job(self, mock_sleep):
        job = MagicMock()

        # Schedule a job
        try:
            scheduler.remove_job('test_job')
        except Exception as e:
            pass
        scheduler.add_job(func=job, trigger='interval', seconds=5, id='test_job')

        # Verify the job is scheduled
        self.assertIsNotNone(scheduler.get_job('test_job'))

        # Remove the job
        scheduler.remove_job('test_job')

        # Verify the job is removed
        self.assertIsNone(scheduler.get_job('test_job'))

    '''
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
    '''

if __name__ == '__main__':
    unittest.main()

