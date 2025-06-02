import unittest
from unittest.mock import patch, sentinel

import app.utils.screenshots as ss


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


if __name__ == "__main__":
    unittest.main()
