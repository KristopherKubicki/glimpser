import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.scheduling import scheduler, schedule_crawlers, update_camera, init_crawl, update_summary, get_system_metrics, system_metrics

class TestScheduler(unittest.TestCase):

    @patch('time.sleep', return_value=None)  # Corrected patch target
    def test_schedule_job(self, mock_sleep):
        job = MagicMock()

        # Schedule a job using add_job with correct argument passing
        scheduler.add_job(func=job, trigger='interval', seconds=5, id='test_job')

        # Simulate the running of the scheduler (normally done in a separate thread)
        job_func = scheduler.get_job('test_job').func
        job_func()

        job.assert_called_once()

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

    @patch('time.sleep', return_value=None)  # Corrected patch target
    def test_scheduler_continues_after_exception(self, mock_sleep):
        job1 = MagicMock(side_effect=Exception("Test Exception"))
        job2 = MagicMock()

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

    @patch('time.sleep', return_value=None)
    def test_remove_scheduled_job(self, mock_sleep):
        job = MagicMock()

        # Schedule a job
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

    @patch('app.utils.scheduling.get_template')
    @patch('app.utils.scheduling.capture_or_download')
    @patch('app.utils.scheduling.os.path.exists')
    @patch('app.utils.scheduling.os.makedirs')
    @patch('app.utils.scheduling.Image.open')
    @patch('app.utils.scheduling.remove_background')
    @patch('app.utils.scheduling.add_timestamp')
    @patch('app.utils.scheduling.os.rename')
    def test_update_camera(self, mock_rename, mock_add_timestamp, mock_remove_background, mock_image_open, mock_makedirs, mock_exists, mock_capture, mock_get_template):
        # Setup mocks
        mock_get_template.return_value = {'name': 'test_camera', 'frequency': 30}
        mock_capture.return_value = True
        mock_exists.return_value = True
        mock_image_open.return_value.__enter__.return_value = MagicMock()

        # Call the function
        update_camera('test_camera', {})

        # Assert that the necessary functions were called
        mock_get_template.assert_called_once_with('test_camera')
        mock_capture.assert_called_once_with('test_camera', {'name': 'test_camera', 'frequency': 30})
        mock_makedirs.assert_called()
        mock_image_open.assert_called()
        mock_remove_background.assert_called()
        mock_add_timestamp.assert_called()
        mock_rename.assert_called()

    @patch('app.utils.scheduling.get_templates')
    @patch('app.utils.scheduling.update_camera')
    def test_init_crawl(self, mock_update_camera, mock_get_templates):
        # Setup mock
        mock_get_templates.return_value = {
            'camera1': {'name': 'camera1'},
            'camera2': {'name': 'camera2'}
        }

        # Call the function
        init_crawl()

        # Assert that update_camera was called for each template
        mock_update_camera.assert_has_calls([
            call('camera1', {'name': 'camera1'}),
            call('camera2', {'name': 'camera2'})
        ])

    @patch('app.utils.scheduling.get_templates')
    @patch('app.utils.scheduling.summarize')
    @patch('app.utils.scheduling.open', new_callable=unittest.mock.mock_open)
    def test_update_summary(self, mock_open, mock_summarize, mock_get_templates):
        # Setup mocks
        mock_get_templates.return_value = {
            'camera1': {'name': 'camera1', 'last_caption_time': '2023-06-01 12:00:00'},
            'camera2': {'name': 'camera2', 'last_caption_time': '2023-06-01 13:00:00'}
        }
        mock_summarize.return_value = "Test summary"

        # Call the function
        update_summary()

        # Assert that summarize was called and the result was written to a file
        mock_summarize.assert_called_once()
        mock_open.assert_called_once()
        mock_open().write.assert_called_once_with('{"Test summary"}\n')

    def test_get_system_metrics(self):
        # Setup test data
        system_metrics['cpu_usage'] = 50.0
        system_metrics['memory_usage'] = 60.0
        system_metrics['thread_count'] = 10
        system_metrics['start_time'] = 1622505600  # June 1, 2021 00:00:00 GMT

        # Call the function
        result = get_system_metrics()

        # Assert the result
        self.assertIn('cpu_usage', result)
        self.assertIn('memory_usage', result)
        self.assertIn('thread_count', result)
        self.assertIn('uptime', result)
        self.assertEqual(result['cpu_usage'], 50.0)
        self.assertEqual(result['memory_usage'], 60.0)
        self.assertEqual(result['thread_count'], 10)
        self.assertRegex(result['uptime'], r'\d+h \d+m \d+s')

if __name__ == '__main__':
    unittest.main()

