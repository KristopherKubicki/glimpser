# tests/test_screenshot_capture.py

import io
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from app.utils.screenshots import capture_screenshot_and_har, download_image


class TestScreenshotCapture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.temp_dir, "test_screenshot.png")
        # Speed up tests by skipping sleeps in the screenshot helper
        self.sleep_patch = patch("app.utils.screenshots.time.sleep", return_value=None)
        self.sleep_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        orig = self.output_path + ".orig.png"
        if os.path.exists(orig):
            os.remove(orig)
        os.rmdir(self.temp_dir)

    @patch("app.utils.screenshots._finalize_screenshot", return_value=True)
    @patch("app.utils.screenshots.launch_headless_chrome")
    @patch("app.utils.screenshots.get_chrome_version", return_value=120)
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_screenshot_success(
        self, mock_online, mock_path, mock_version, mock_launch, mock_finalize
    ):
        mock_driver = MagicMock()
        mock_launch.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True

        result = capture_screenshot_and_har("http://example.com", self.output_path)

        self.assertTrue(result)
        mock_driver.get.assert_called_once_with("http://example.com")
        mock_driver.save_screenshot.assert_called()
        mock_finalize.assert_called_once()

    @patch("app.utils.screenshots._finalize_screenshot", return_value=True)
    @patch("app.utils.screenshots.launch_headless_chrome")
    @patch("app.utils.screenshots.get_chrome_version", return_value=120)
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_screenshot_with_popup(
        self, mock_online, mock_path, mock_version, mock_launch, mock_finalize
    ):
        mock_driver = MagicMock()
        mock_launch.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True
        mock_driver.find_elements.return_value = [MagicMock()]

        # Call the function with a popup_xpath
        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, popup_xpath="//div[@class='popup']"
        )

        self.assertTrue(result)
        mock_driver.find_elements.assert_called_once()
        mock_driver.execute_script.assert_called_once()
        mock_finalize.assert_called_once()

    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_screenshot_failure(self, mock_online, mock_chrome):
        # Mock the Chrome driver to raise an exception
        mock_chrome.side_effect = Exception("Browser error")

        # Call the function
        result = capture_screenshot_and_har("http://example.com", self.output_path)

        # Assertions
        self.assertFalse(result)
        self.assertFalse(os.path.exists(self.output_path))

    @patch("app.utils.screenshots.launch_headless_chrome")
    @patch("app.utils.screenshots.get_chrome_version", return_value=120)
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
    @patch("app.utils.screenshots.create_placeholder")
    @patch("app.utils.screenshots.is_mostly_blank", return_value=True)
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_screenshot_blank_image(
        self,
        mock_online,
        mock_blank,
        mock_placeholder,
        mock_get_path,
        mock_get_version,
        mock_launch,
    ):
        mock_driver = MagicMock()
        mock_launch.return_value = mock_driver
        mock_driver.get.return_value = None

        partial = self.output_path + ".tmp.png"

        def fake_save(path):
            Image.new("RGB", (1, 1)).save(partial)
            return True

        mock_driver.save_screenshot.side_effect = fake_save
        mock_placeholder.side_effect = lambda path, name: Image.new("RGB", (1, 1)).save(
            path
        )

        result = capture_screenshot_and_har("http://example.com", self.output_path)

        self.assertFalse(result)
        self.assertTrue(os.path.exists(self.output_path))
        self.assertTrue(os.path.exists(self.output_path + ".orig.png"))
        self.assertFalse(os.path.exists(partial))
        mock_blank.assert_called()
        mock_placeholder.assert_called_once()

    @patch("app.utils.screenshots._finalize_screenshot", return_value=True)
    @patch("app.utils.screenshots.launch_headless_chrome")
    @patch("app.utils.screenshots.get_chrome_version", return_value=120)
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_screenshot_with_dark_mode(
        self, mock_online, mock_path, mock_version, mock_launch, mock_finalize
    ):
        mock_driver = MagicMock()
        mock_launch.return_value = mock_driver
        mock_driver.get.return_value = None
        mock_driver.save_screenshot.return_value = True

        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, dark=True
        )

        self.assertTrue(result)
        mock_driver.execute_cdp_cmd.assert_called_with(
            "Emulation.setAutoDarkModeOverride", {"enabled": True}
        )
        mock_finalize.assert_called_once()

    @patch("app.utils.screenshots.config.REQUEST_VERIFY_SSL", False)
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

    @patch("app.utils.screenshots.config.REQUEST_VERIFY_SSL", False)
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


if __name__ == "__main__":
    unittest.main()
