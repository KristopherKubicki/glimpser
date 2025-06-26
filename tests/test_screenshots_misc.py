import os
import unittest
from unittest.mock import MagicMock, patch, sentinel

from requests.structures import CaseInsensitiveDict

import app.utils.browser as browser


class TestHttpSession(unittest.TestCase):
    @patch("app.utils.browser.requests.Session")
    def test_http_session_singleton_and_headers(self, mock_session_cls):
        session_instance = MagicMock()
        session_instance.headers = CaseInsensitiveDict()
        mock_session_cls.return_value = session_instance

        browser._session = None

        sess1 = browser.http_session()
        sess2 = browser.http_session()

        self.assertIs(sess1, sess2)
        mock_session_cls.assert_called_once()
        self.assertIn("User-Agent", sess1.headers)
        self.assertIn("Accept", sess1.headers)


class TestGetDriver(unittest.TestCase):
    def setUp(self):
        if hasattr(browser._driver_local, "driver"):
            browser._driver_local.driver = None

    def tearDown(self):
        if hasattr(browser._driver_local, "driver"):
            browser._driver_local.driver = None

    def test_driver_cached(self):
        with (
            patch(
                "app.utils.browser.ChromeDriverManager.install",
                return_value=sentinel.binary,
            ) as mock_install,
            patch(
                "app.utils.browser.webdriver.Chrome",
                return_value=sentinel.driver,
            ) as mock_chrome,
            patch("app.utils.browser.is_system_online", return_value=True),
        ):
            driver1 = browser.get_driver(sentinel.options)
            driver2 = browser.get_driver(sentinel.options)
            self.assertIs(driver1, sentinel.driver)
            self.assertIs(driver1, driver2)
            mock_install.assert_called_once()
            mock_chrome.assert_called_once()


if __name__ == "__main__":
    unittest.main()
