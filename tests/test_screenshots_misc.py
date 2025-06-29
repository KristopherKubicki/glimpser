import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from requests.structures import CaseInsensitiveDict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from unittest.mock import patch, sentinel

import app.utils.screenshots as ss


class TestHttpSession(unittest.TestCase):
    @patch("app.utils.screenshots.requests.Session")
    def test_http_session_singleton_and_headers(self, mock_session_cls):
        session_instance = MagicMock()
        session_instance.headers = CaseInsensitiveDict()
        mock_session_cls.return_value = session_instance

        ss._session = None

        sess1 = ss.http_session()
        sess2 = ss.http_session()

        self.assertIs(sess1, sess2)
        mock_session_cls.assert_called_once()
        self.assertIn("User-Agent", sess1.headers)
        self.assertIn("Accept", sess1.headers)


class TestGetDriver(unittest.TestCase):
    def setUp(self):
        ss._DRIVER = None

    def tearDown(self):
        ss._DRIVER = None

    def test_driver_cached(self):
        with patch(
            "app.utils.screenshots.ChromeDriverManager.install",
            return_value=sentinel.binary,
        ) as mock_install, patch(
            "app.utils.screenshots.webdriver.Chrome",
            return_value=sentinel.driver,
        ) as mock_chrome:
            driver1 = ss.get_driver(sentinel.options)
            driver2 = ss.get_driver(sentinel.options)
            self.assertIs(driver1, sentinel.driver)
            self.assertIs(driver1, driver2)
            mock_install.assert_called_once()
            mock_chrome.assert_called_once()

    def test_kill_driver_process_handles_missing_proc(self):
        class DummyService:
            process = None

        class DummyDriver:
            service = DummyService()

        ss._DRIVER = object()
        # Should not raise when process attribute is None
        ss.kill_driver_process(DummyDriver())
        self.assertIsNone(ss._DRIVER)


if __name__ == "__main__":
    unittest.main()
