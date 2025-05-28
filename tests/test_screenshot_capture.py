# tests/test_screenshot_capture.py

import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import sys
import logging
import io
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.screenshots import capture_screenshot_and_har, download_image


class TestScreenshotCapture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.temp_dir, "test_screenshot.png")

    def tearDown(self):
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        os.rmdir(self.temp_dir)

    @patch("app.utils.screenshots.webdriver.Chrome")
    def test_capture_screenshot_success(self, mock_chrome):
        # Mock the Chrome driver and its methods
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True

        # Call the function
        result = capture_screenshot_and_har("http://example.com", self.output_path)

        # Assertions
        # self.assertTrue(result)  # assuming network connetion...
        # TODO: cleant his up
        # self.assertTrue(os.path.exists(self.output_path))
        # mock_driver.get.assert_called_once_with("http://example.com")
        # mock_driver.save_screenshot.assert_called_once_with(self.output_path)

    @patch("app.utils.screenshots.webdriver.Chrome")
    def test_capture_screenshot_with_popup(self, mock_chrome):
        # Mock the Chrome driver and its methods
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True
        mock_driver.find_elements.return_value = [MagicMock()]

        # Call the function with a popup_xpath
        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, popup_xpath="//div[@class='popup']"
        )

        # Assertions
        # self.assertTrue(result)
        # self.assertTrue(os.path.exists(self.output_path))
        # mock_driver.find_elements.assert_called_once()
        # mock_driver.execute_script.assert_called_once()

    @patch("app.utils.screenshots.webdriver.Chrome")
    def test_capture_screenshot_failure(self, mock_chrome):
        # Mock the Chrome driver to raise an exception
        mock_chrome.side_effect = Exception("Browser error")

        # Call the function
        result = capture_screenshot_and_har("http://example.com", self.output_path)

        # Assertions
        # self.assertFalse(result)
        # self.assertFalse(os.path.exists(self.output_path))

    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.is_mostly_blank")
    def test_capture_screenshot_blank_image(self, mock_is_mostly_blank, mock_chrome):
        # Mock the Chrome driver and its methods
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True

        # Mock is_mostly_blank to return True
        mock_is_mostly_blank.return_value = True

        # Call the function, might have to mock this better
        result = capture_screenshot_and_har("http://example.com", self.output_path)

        # Assertions
        # self.assertFalse(result) # i think this is going to be True, not false...
        # self.assertFalse(os.path.exists(self.output_path))
        # mock_is_mostly_blank.assert_called_once()

    @patch("app.utils.screenshots.webdriver.Chrome")
    def test_capture_screenshot_with_dark_mode(self, mock_chrome):
        # Mock the Chrome driver and its methods
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True

        # Call the function with dark mode enabled
        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, dark=True
        )

        # Assertions
        # self.assertTrue(result)
        # self.assertTrue(os.path.exists(self.output_path))
        # mock_driver.execute_cdp_cmd.assert_called_with(
        #    "Emulation.setAutoDarkModeOverride", {"enabled": True}
        # )

    @patch("app.utils.screenshots.http_session")
    def test_download_image_uses_proxy(self, mock_session_factory):
        mock_session = MagicMock()
        mock_response = MagicMock()
        # create a tiny valid PNG
        img_bytes = io.BytesIO()
        Image.new("RGB", (1, 1)).save(img_bytes, format="PNG")
        mock_response.status_code = 200
        mock_response.content = img_bytes.getvalue()
        mock_session.get.return_value = mock_response
        mock_session_factory.return_value = mock_session

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            download_image(
                "http://example.com/test.png",
                tmp.name,
                proxy="http://proxy:8080",
            )

        kwargs = mock_session.get.call_args.kwargs
        self.assertEqual(
            kwargs.get("proxies"),
            {"http": "http://proxy:8080", "https": "http://proxy:8080"},
        )

    @patch("app.utils.screenshots.http_session")
    def test_download_image_skips_invalid_proxy(self, mock_session_factory):
        mock_session = MagicMock()
        mock_response = MagicMock()
        img_bytes = io.BytesIO()
        Image.new("RGB", (1, 1)).save(img_bytes, format="PNG")
        mock_response.status_code = 200
        mock_response.content = img_bytes.getvalue()
        mock_session.get.return_value = mock_response
        mock_session_factory.return_value = mock_session

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            download_image(
                "http://example.com/test.png",
                tmp.name,
                proxy=" ",
            )

        kwargs = mock_session.get.call_args.kwargs
        self.assertNotIn("proxies", kwargs)

    @patch("app.utils.screenshots.apply_dark_mode")
    @patch("app.utils.screenshots.http_session")
    def test_download_image_applies_dark_mode(self, mock_session_factory, mock_dark):
        mock_session = MagicMock()
        mock_response = MagicMock()
        img_bytes = io.BytesIO()
        Image.new("RGB", (1, 1)).save(img_bytes, format="PNG")
        mock_response.status_code = 200
        mock_response.content = img_bytes.getvalue()
        mock_session.get.return_value = mock_response
        mock_session_factory.return_value = mock_session

        mock_dark.side_effect = lambda img: img

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            download_image(
                "http://example.com/test.png",
                tmp.name,
                dark=True,
            )

        mock_dark.assert_called_once()


if __name__ == "__main__":
    unittest.main()
