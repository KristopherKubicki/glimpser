import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.network import _get_test_hosts, is_system_online


class TestIsSystemOnline(unittest.TestCase):
    @patch("socket.create_connection")
    def test_first_host_success(self, mock_conn):
        mock_conn.return_value = None
        with patch.dict(os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1"}):
            self.assertTrue(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 53), timeout=1)

    @patch("socket.create_connection", side_effect=OSError)
    def test_all_hosts_fail(self, mock_conn):
        with patch.dict(os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1,2.2.2.2"}):
            self.assertFalse(is_system_online())
            self.assertEqual(mock_conn.call_count, 2)

    def test_get_test_hosts_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_test_hosts(), ["8.8.8.8", "1.1.1.1"])

    @patch("app.utils.network.socket.create_connection")
    @patch("app.utils.network._get_test_hosts", return_value=[" ", "2.2.2.2"])
    def test_is_system_online_skips_blank(self, mock_hosts, mock_conn):
        mock_conn.return_value = None
        self.assertTrue(is_system_online(timeout=2))
        mock_conn.assert_called_once_with(("2.2.2.2", 53), timeout=2)

    @patch("app.utils.network.logging.warning")
    @patch("app.utils.network.socket.create_connection", side_effect=OSError("fail"))
    def test_logs_when_all_fail(self, mock_conn, mock_warn):
        with patch("app.utils.network._get_test_hosts", return_value=["1.1.1.1"]):
            self.assertFalse(is_system_online(timeout=1))
        mock_conn.assert_called_once_with(("1.1.1.1", 53), timeout=1)
        mock_warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
