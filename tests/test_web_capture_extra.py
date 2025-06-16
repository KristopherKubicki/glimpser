import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import app.utils.screenshots as ss


class TestDangerMode(unittest.TestCase):
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=False)
    @patch("app.utils.screenshots.check_user_activity")
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_danger_port_closed(self, mock_online, mock_path, mock_activity, mock_port):
        result = ss.capture_screenshot_and_har(
            "http://example.com", "out.png", danger=True
        )
        self.assertFalse(result)
        mock_activity.assert_not_called()

    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=True)
    @patch("app.utils.screenshots.check_user_activity", return_value=True)
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_danger_user_active(self, mock_online, mock_path, mock_activity, mock_port):
        result = ss.capture_screenshot_and_har(
            "http://example.com", "out.png", danger=True
        )
        self.assertFalse(result)

    @patch("app.utils.screenshots._finalize_screenshot", return_value=True)
    @patch("app.utils.screenshots._capture_danger_mode", return_value=True)
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=True)
    @patch("app.utils.screenshots.check_user_activity", return_value=False)
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_danger_success(
        self,
        mock_online,
        mock_path,
        mock_activity,
        mock_port,
        mock_capture,
        mock_finalize,
    ):
        result = ss.capture_screenshot_and_har(
            "http://example.com", "out.png", danger=True
        )
        self.assertTrue(result)
        mock_capture.assert_called_once()
        mock_finalize.assert_called_once()


class TestDedicatedSelector(unittest.TestCase):
    @patch("app.utils.screenshots._finalize_screenshot", return_value=True)
    @patch("app.utils.screenshots.launch_headless_chrome")
    @patch("app.utils.screenshots.get_chrome_version", return_value=120)
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_with_dedicated_selector(
        self, mock_online, mock_path, mock_version, mock_launch, mock_finalize
    ):
        mock_driver = MagicMock()
        element = MagicMock()
        mock_driver.find_element.return_value = element
        mock_launch.return_value = mock_driver
        mock_driver.save_screenshot.return_value = True
        mock_driver.get.return_value = None

        result = ss.capture_screenshot_and_har(
            "http://example.com",
            "out.png",
            dedicated_selector="//div",
        )

        self.assertTrue(result)
        mock_driver.find_element.assert_called_once()
        element.screenshot.assert_called_once()
        mock_finalize.assert_called_once()

    @patch("app.utils.screenshots._finalize_screenshot", return_value=True)
    @patch("app.utils.screenshots.launch_headless_chrome")
    @patch("app.utils.screenshots.get_chrome_version", return_value=120)
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_capture_falls_back_when_selector_missing(
        self, mock_online, mock_path, mock_version, mock_launch, mock_finalize
    ):
        mock_driver = MagicMock()
        mock_driver.find_element.side_effect = Exception("no el")
        mock_launch.return_value = mock_driver
        mock_driver.save_screenshot.return_value = True
        mock_driver.get.return_value = None

        result = ss.capture_screenshot_and_har(
            "http://example.com",
            "out.png",
            dedicated_selector="//div",
        )

        self.assertTrue(result)
        mock_driver.save_screenshot.assert_called_once()
        mock_finalize.assert_called_once()


class TestSaveHar(unittest.TestCase):
    def test_save_har_logs(self):
        driver = MagicMock()
        driver.get_log.return_value = [
            {"level": "INFO", "message": "msg", "timestamp": 1}
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.har")
            ss._save_har_logs(driver, path)
            with open(path) as f:
                content = f.read().strip()
        self.assertEqual(content, "msg")
        driver.get_log.assert_called_once_with("performance")


class TestCaptureOrDownloadFallback(unittest.TestCase):
    @patch("app.utils.screenshots.capture_screenshot_and_har", return_value=True)
    @patch("app.utils.screenshots.capture_screenshot_phantom", return_value=False)
    @patch("app.utils.screenshots.capture_screenshot_and_har_light", return_value=False)
    @patch("app.utils.screenshots.should_use_phantom_browser", return_value=False)
    @patch("app.utils.screenshots.should_use_lightweight_browser", return_value=True)
    @patch("app.utils.screenshots.get_content_type", return_value=("text/html", True))
    @patch("app.utils.screenshots.is_address_reachable", return_value=True)
    def test_fallback_to_full_browser(
        self,
        mock_reach,
        mock_ctype,
        mock_use_light,
        mock_use_phantom,
        mock_light,
        mock_phantom,
        mock_full,
    ):
        result = ss.capture_or_download("name", {"url": "http://example.com"})
        self.assertTrue(result)
        mock_full.assert_called_once()
