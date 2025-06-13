import unittest
from unittest.mock import MagicMock, patch

from app.utils import console_dashboard


class TestConsoleDashboard(unittest.TestCase):
    @patch("app.utils.console_dashboard.curses.wrapper")
    def test_main_wraps_render(self, mock_wrapper):
        console_dashboard.main()
        mock_wrapper.assert_called_once_with(console_dashboard._render)


if __name__ == "__main__":
    unittest.main()
