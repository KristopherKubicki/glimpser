"""Tests for capture danger mode."""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.utils.screenshots import capture_screenshot_and_har


class TestDangerModeCapture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.temp_dir, "shot.png")

    def tearDown(self):
        for fname in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, fname))
        os.rmdir(self.temp_dir)

    def _mock_driver(self):
        driver = MagicMock()
        driver.current_window_handle = "w1"
        driver.window_handles = ["w1", "w2"]
        driver.switch_to.window = MagicMock()
        driver.set_page_load_timeout = MagicMock()
        driver.execute_script = MagicMock()
        driver.get = MagicMock()
        driver.close = MagicMock()

        def save_screenshot(path):
            with open(path, "wb") as f:
                f.write(b"x")
            return True

        driver.save_screenshot.side_effect = save_screenshot
        driver.find_element.side_effect = Exception("no el")
        return driver

    @patch("app.utils.screenshots._send_input_event")
    @patch("app.utils.screenshots._finalize_screenshot")
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.check_user_activity", return_value=False)
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=True)
    @patch("app.utils.screenshots.time.sleep", return_value=None)
    def test_success(
        self,
        _sleep,
        mock_port,
        mock_user_idle,
        mock_webdriver,
        mock_online,
        mock_path,
        mock_finalize,
        _send_input,
    ):
        driver = self._mock_driver()
        mock_webdriver.return_value = driver

        def finalize(partial, final, name, invert, dark):
            os.rename(partial, final)
            return True

        mock_finalize.side_effect = finalize

        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, danger=True
        )

        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.output_path))
        options = mock_webdriver.call_args.kwargs["options"]
        self.assertEqual(options.debugger_address, "127.0.0.1:9222")

    @patch("app.utils.screenshots._send_input_event")
    @patch("app.utils.screenshots._finalize_screenshot")
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.check_user_activity", return_value=True)
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=True)
    def test_user_activity(
        self,
        mock_port,
        mock_user_active,
        mock_webdriver,
        mock_online,
        mock_path,
        _finalize,
        _send_input,
    ):
        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, danger=True
        )

        self.assertFalse(result)
        mock_webdriver.assert_not_called()
        self.assertFalse(os.path.exists(self.output_path))

    @patch("app.utils.screenshots._send_input_event")
    @patch("app.utils.screenshots._finalize_screenshot")
    @patch("app.utils.screenshots.get_chrome_path", return_value="/usr/bin/chrome")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.check_user_activity", return_value=False)
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=False)
    def test_port_closed(
        self,
        mock_port,
        mock_user_idle,
        mock_webdriver,
        mock_online,
        mock_path,
        _finalize,
        _send_input,
    ):
        result = capture_screenshot_and_har(
            "http://example.com", self.output_path, danger=True
        )

        self.assertFalse(result)
        mock_webdriver.assert_not_called()
        self.assertFalse(os.path.exists(self.output_path))


if __name__ == "__main__":
    unittest.main()
