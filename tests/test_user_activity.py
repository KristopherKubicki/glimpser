"""Tests for user activity."""
import unittest
from unittest.mock import patch

from app.utils.screenshots import check_user_activity


class TestUserActivityNonLinux(unittest.TestCase):
    @patch("app.utils.screenshots.platform.system", return_value="Windows")
    def test_windows_idle_detection(self, mock_system):
        with (
            patch("app.utils.screenshots.idle_seconds_x11", side_effect=RuntimeError),
            patch(
                "app.utils.screenshots.idle_seconds_loginctl", side_effect=RuntimeError
            ),
            patch("app.utils.screenshots.idle_seconds_windows", return_value=10),
            patch("app.utils.screenshots._safe_import_pynput"),
            patch("app.utils.screenshots.mouse", None),
            patch("app.utils.screenshots.keyboard", None),
        ):
            self.assertTrue(check_user_activity(timeout=1))

    @patch("app.utils.screenshots.platform.system", return_value="Darwin")
    def test_macos_idle_detection(self, mock_system):
        with (
            patch("app.utils.screenshots.idle_seconds_x11", side_effect=RuntimeError),
            patch(
                "app.utils.screenshots.idle_seconds_loginctl", side_effect=RuntimeError
            ),
            patch("app.utils.screenshots.idle_seconds_macos", return_value=10),
            patch("app.utils.screenshots._safe_import_pynput"),
            patch("app.utils.screenshots.mouse", None),
            patch("app.utils.screenshots.keyboard", None),
        ):
            self.assertTrue(check_user_activity(timeout=1))


if __name__ == "__main__":
    unittest.main()
