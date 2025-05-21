import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.network_testing import network_idle_condition, check_network_errors, wait_for_element
from selenium.webdriver.common.by import By

class TestNetworkTesting(unittest.TestCase):
    @patch('time.sleep', return_value=None)
    def test_network_idle_condition_success(self, _):
        driver = MagicMock()
        log_entry = {'message': json.dumps({'message': {'params': {'response': {'url': 'http://example.com', 'status': 200}}}})}
        driver.get_log.side_effect = [[log_entry], []]
        ok, status = network_idle_condition(driver, 'http://example.com', timeout=0.1, idle_time=0)
        self.assertTrue(ok)
        self.assertEqual(status, 200)

    @patch('time.sleep', return_value=None)
    def test_network_idle_condition_error(self, _):
        driver = MagicMock()
        log_entry = {'message': json.dumps({'message': {'params': {'response': {'url': 'http://example.com', 'status': 404}}}})}
        driver.get_log.return_value = [log_entry]
        ok, status = network_idle_condition(driver, 'http://example.com', timeout=0.1, idle_time=0)
        self.assertFalse(ok)
        self.assertEqual(status, 404)

    @patch('time.sleep', return_value=None)
    def test_check_network_errors(self, _):
        driver = MagicMock()
        error_log = {'level': 'SEVERE', 'message': 'Failed to load resource'}
        driver.get_log.side_effect = [[error_log], []]
        found, errors = check_network_errors(driver, 'http://example.com', timeout=0.1)
        self.assertTrue(found)
        self.assertIn('Failed to load resource', errors[0])

    @patch('time.sleep', return_value=None)
    def test_wait_for_element(self, _):
        driver = MagicMock()
        element = object()
        driver.find_element.return_value = element
        result = wait_for_element(driver, '#id', timeout=0.1)
        self.assertIs(result, element)
        driver.find_element.assert_called_with(By.CSS_SELECTOR, '#id')

        driver.find_element.side_effect = Exception()
        result = wait_for_element(driver, '#id', timeout=0.1)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
