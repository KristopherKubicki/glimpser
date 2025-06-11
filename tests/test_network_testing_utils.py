import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import unittest
from unittest.mock import patch

from app.utils.network_testing import (
    check_network_errors,
    network_idle_condition,
    wait_for_element,
)


class DummyDriver:
    def __init__(self, performance_logs=None, browser_logs=None, element=None):
        self.performance_logs = performance_logs or []
        self.browser_logs = browser_logs or []
        self.element = element

    def get_log(self, log_type):
        if log_type == "performance":
            return self.performance_logs.pop(0) if self.performance_logs else []
        if log_type == "browser":
            return self.browser_logs.pop(0) if self.browser_logs else []
        return []

    def find_element(self, by, selector):
        if self.element is not None:
            return self.element
        raise Exception("not found")


class TestNetworkTestingUtils(unittest.TestCase):
    def _time_gen(self, start=0.0, step=0.1):
        """Generate an increasing sequence of times.

        The first value is repeated so the initial call sets the timeout
        and the loop condition uses the same timestamp.
        """
        current = start
        first = True
        while True:
            yield current
            if first:
                first = False
            else:
                current += step

    def test_network_idle_condition_success(self):
        log = {
            "message": json.dumps(
                {
                    "message": {
                        "method": "Network.responseReceived",
                        "params": {"response": {"url": "http://ex", "status": 200}},
                    }
                }
            )
        }
        driver = DummyDriver(performance_logs=[[log]])
        gen = self._time_gen()
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, status = network_idle_condition(driver, "http://ex", timeout=0.1, idle_time=0)
        self.assertTrue(result)
        self.assertEqual(status, 200)

    def test_network_idle_condition_failure_status(self):
        log = {
            "message": json.dumps(
                {
                    "message": {
                        "method": "Network.responseReceived",
                        "params": {"response": {"url": "http://ex", "status": 404}},
                    }
                }
            )
        }
        driver = DummyDriver(performance_logs=[[log]])
        gen = self._time_gen()
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, status = network_idle_condition(driver, "http://ex", timeout=0.1, idle_time=0)
        self.assertFalse(result)
        self.assertEqual(status, 404)

    def test_network_idle_condition_server_error(self):
        log = {
            "message": json.dumps(
                {
                    "message": {
                        "method": "Network.responseReceived",
                        "params": {"response": {"url": "http://ex", "status": 500}},
                    }
                }
            )
        }
        driver = DummyDriver(performance_logs=[[log]])
        gen = self._time_gen()
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, status = network_idle_condition(driver, "http://ex", timeout=0.1, idle_time=0)
        self.assertFalse(result)
        self.assertEqual(status, 500)

    def test_network_idle_condition_stealth(self):
        driver = DummyDriver()
        gen = self._time_gen(step=0.2)
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, status = network_idle_condition(driver, "http://ex", timeout=1, idle_time=0, stealth=True)
        self.assertFalse(result)
        self.assertEqual(status, 800)

    def test_network_idle_condition_skips_bad_logs(self):
        bad = {"message": "Network.response not-json"}
        driver = DummyDriver(performance_logs=[[bad]])
        gen = self._time_gen(step=0.2)
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, status = network_idle_condition(driver, "http://ex", timeout=0.5, idle_time=0)
        self.assertTrue(result)
        self.assertEqual(status, 800)

    def test_check_network_errors_no_error(self):
        driver = DummyDriver(browser_logs=[[{"level": "INFO", "message": "ok"}]])
        gen = self._time_gen()
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, errors = check_network_errors(driver, "http://ex", timeout=0.1)
        self.assertFalse(result)
        self.assertEqual(errors, [])

    def test_check_network_errors_detects_error(self):
        driver = DummyDriver(browser_logs=[[{"level": "SEVERE", "message": "Failed to load resource"}]])
        gen = self._time_gen()
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            result, errors = check_network_errors(driver, "http://ex", timeout=0.1)
        self.assertTrue(result)
        self.assertEqual(len(errors), 1)

    def test_wait_for_element_found(self):
        element = object()
        driver = DummyDriver(element=element)
        gen = self._time_gen()
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            found = wait_for_element(driver, "div")
        self.assertIs(found, element)

    def test_wait_for_element_not_found(self):
        driver = DummyDriver()
        gen = self._time_gen(step=0.2)
        with patch("time.time", side_effect=gen), patch("time.sleep"):
            found = wait_for_element(driver, "div", timeout=0.5)
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
