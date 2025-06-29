"""Tests for console dashboard."""
import unittest
from unittest.mock import MagicMock, patch

from app.utils import console_dashboard


class TestConsoleDashboard(unittest.TestCase):
    @patch("app.utils.console_dashboard.curses.wrapper")
    def test_main_wraps_render(self, mock_wrapper):
        console_dashboard.main()
        mock_wrapper.assert_called_once_with(console_dashboard._render)

    @patch("app.utils.console_dashboard.get_feed_status")
    @patch("app.utils.console_dashboard.curses")
    def test_render_quits_on_q(self, mock_curses, mock_get_status):
        screen = MagicMock()
        screen.getmaxyx.return_value = (10, 40)
        screen.getch.side_effect = [ord("q")]
        mock_get_status.return_value = [
            {
                "name": "cam1",
                "status": "ok",
                "last_screenshot_display": "",
                "last_caption_display": "",
            }
        ]

        console_dashboard._render(screen)

        screen.timeout.assert_called_once_with(
            console_dashboard.REFRESH_INTERVAL * 1000
        )
        screen.refresh.assert_called()
        self.assertEqual(screen.getch.call_count, 1)

    @patch("app.utils.console_dashboard.get_feed_status")
    @patch("app.utils.console_dashboard.curses")
    def test_render_refreshes_after_timeout(self, mock_curses, mock_get_status):
        screen = MagicMock()
        screen.getmaxyx.return_value = (10, 40)
        screen.getch.side_effect = [-1, ord("q")]
        mock_get_status.side_effect = [
            [
                {
                    "name": "cam1",
                    "status": "ok",
                    "last_screenshot_display": "",
                    "last_caption_display": "",
                }
            ],
            [
                {
                    "name": "cam1",
                    "status": "ok",
                    "last_screenshot_display": "",
                    "last_caption_display": "",
                }
            ],
        ]

        console_dashboard._render(screen)

        self.assertEqual(mock_get_status.call_count, 2)
        self.assertEqual(screen.refresh.call_count, 2)


if __name__ == "__main__":
    unittest.main()
