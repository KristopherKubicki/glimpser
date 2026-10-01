import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.utils.screenshots import capture_screenshot_and_har


class TestDangerModeCapture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.temp_dir, "shot.png")
        # Capture tests must not inspect or clean up the operator's browsers.
        overrides = {
            "cleanup_old_tempdirs": None,
            "cleanup_orphaned_browser_processes": None,
            "_acquire_browser_capture_file_lock": (True, None),
            "get_chrome_version": 120,
            "_danger_session_status": None,
            "_browser_profile_chrome_args": [],
            "_persist_preflight_cache": None,
            "kill_driver_process": None,
        }
        for name, result in overrides.items():
            mocked = patch(f"app.utils.screenshots.{name}", return_value=result)
            mocked.start()
            self.addCleanup(mocked.stop)
        sleeper = patch("app.utils.screenshots.time.sleep", return_value=None)
        sleeper.start()
        self.addCleanup(sleeper.stop)
        cache = patch("app.utils.screenshots.throttle_cache", {})
        cache.start()
        self.addCleanup(cache.stop)

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
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
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

        def finalize(partial, final, name, invert, dark, **_kwargs):
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
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.check_user_activity", return_value=True)
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=True)
    def test_user_activity_uses_isolated_headless_browser(
        self,
        mock_port,
        mock_user_active,
        mock_webdriver,
        mock_online,
        mock_path,
        _finalize,
        _send_input,
    ):
        driver = self._mock_driver()
        driver.execute_script.return_value = ""
        _finalize.return_value = True
        with (
            patch(
                "app.utils.screenshots.launch_headless_chrome", return_value=driver
            ) as launch,
            patch("app.utils.screenshots._capture_danger_mode") as attached,
        ):
            result = capture_screenshot_and_har(
                "http://example.com", self.output_path, danger=True, stealth=False
            )
        self.assertTrue(result)
        attached.assert_not_called()
        mock_webdriver.assert_not_called()
        options = launch.call_args.args[0]
        self.assertIn("--headless=new", options.arguments)
        self.assertFalse(options.debugger_address)
        self.assertTrue(
            any(arg.startswith("--user-data-dir=") for arg in options.arguments)
        )
        driver.quit.assert_called_once()

    @patch("app.utils.screenshots._send_input_event")
    @patch("app.utils.screenshots._finalize_screenshot")
    @patch("app.utils.screenshots.get_chrome_path", return_value=sys.executable)
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch("app.utils.screenshots.webdriver.Chrome")
    @patch("app.utils.screenshots.check_user_activity", return_value=False)
    @patch("app.utils.screenshots.is_chrome_debug_port_open", return_value=False)
    def test_port_closed_uses_isolated_headless_browser(
        self,
        mock_port,
        mock_user_idle,
        mock_webdriver,
        mock_online,
        mock_path,
        _finalize,
        _send_input,
    ):
        driver = self._mock_driver()
        driver.execute_script.return_value = ""
        _finalize.return_value = True
        with (
            patch(
                "app.utils.screenshots.launch_headless_chrome", return_value=driver
            ) as launch,
            patch("app.utils.screenshots._capture_danger_mode") as attached,
        ):
            result = capture_screenshot_and_har(
                "http://example.com", self.output_path, danger=True, stealth=False
            )
        self.assertTrue(result)
        attached.assert_not_called()
        mock_webdriver.assert_not_called()
        options = launch.call_args.args[0]
        self.assertIn("--headless=new", options.arguments)
        self.assertFalse(options.debugger_address)
        self.assertTrue(
            any(arg.startswith("--user-data-dir=") for arg in options.arguments)
        )
        driver.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
