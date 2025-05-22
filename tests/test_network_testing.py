import unittest
import json
from unittest.mock import MagicMock, patch

from app.utils.network_testing import network_idle_condition, check_network_errors, wait_for_element

class FakeTime:
    def __init__(self):
        self.current = 0.0
    def __call__(self):
        self.current += 0.1
        return self.current

class TestNetworkTesting(unittest.TestCase):
    def setUp(self):
        self.fake_time = FakeTime()
        self.time_patcher = patch('app.utils.network_testing.time.time', side_effect=self.fake_time)
        self.sleep_patcher = patch('app.utils.network_testing.time.sleep', return_value=None)
        self.time_patcher.start()
        self.sleep_patcher.start()

    def tearDown(self):
        self.time_patcher.stop()
        self.sleep_patcher.stop()

    def test_network_idle_condition_success(self):
        driver = MagicMock()
        log = {"message": json.dumps({"message": {"params": {"response": {"url": "http://example.com", "status": 200}}}})}
        driver.get_log.side_effect = [[log], []]
        result, status = network_idle_condition(driver, "http://example.com", timeout=0.2, idle_time=0)
        self.assertTrue(result)
        self.assertEqual(status, 200)

    def test_network_idle_condition_error(self):
        driver = MagicMock()
        log = {"message": json.dumps({"message": {"params": {"response": {"url": "http://example.com", "status": 404}}}})}
        driver.get_log.side_effect = [[log], []]
        result, status = network_idle_condition(driver, "http://example.com", timeout=0.2, idle_time=0)
        self.assertFalse(result)
        self.assertEqual(status, 404)

    def test_check_network_errors_found(self):
        driver = MagicMock()
        driver.get_log.side_effect = [[{"level": "SEVERE", "message": "Failed to load resource"}], []]
        found, errors = check_network_errors(driver, "http://example.com", timeout=0.2)
        self.assertTrue(found)
        self.assertEqual(errors, ["Failed to load resource"])

    def test_check_network_errors_none(self):
        driver = MagicMock()
        driver.get_log.side_effect = [[], []]
        found, errors = check_network_errors(driver, "http://example.com", timeout=0.2)
        self.assertFalse(found)
        self.assertEqual(errors, [])

    def test_wait_for_element_success(self):
        driver = MagicMock()
        element = object()
        driver.find_element.side_effect = [Exception(), element]
        result = wait_for_element(driver, "div.item", timeout=0.2)
        self.assertIs(result, element)

    def test_wait_for_element_timeout(self):
        driver = MagicMock()
        driver.find_element.side_effect = Exception()
        result = wait_for_element(driver, "div.item", timeout=0.2)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
