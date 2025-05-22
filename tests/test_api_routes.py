import unittest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import create_app

class TestAPIRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app(watchdog=False, schedule=False)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_health_requires_auth(self):
        resp = self.client.get('/health')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

    @patch('app.routes.SessionLocal')
    @patch('app.routes.scheduling')
    def test_health_with_key(self, mock_sched, mock_session):
        mock_sched.get_system_metrics.return_value = {
            'cpu_usage': 1,
            'memory_usage': 1,
            'thread_count': 1,
            'open_files': 1,
            'disk_usage': 1,
            'uptime': '1h 0m 0s'
        }
        mock_sched.scheduler.running = True
        mock_session.return_value.execute.return_value = None
        mock_session.return_value.close.return_value = None
        with patch('app.routes.API_KEY', 'secret'):
            resp = self.client.get('/health', headers={'X-API-Key': 'secret'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('status', data)
        self.assertIn('metrics', data)

    @patch('app.routes.template_manager.get_templates', return_value={'t1': {}})
    def test_templates_endpoint(self, mock_get):
        with patch('app.routes.API_KEY', 'secret'):
            resp = self.client.get('/templates?group=all', headers={'X-API-Key': 'secret'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {'t1': {}})

if __name__ == '__main__':
    unittest.main()
