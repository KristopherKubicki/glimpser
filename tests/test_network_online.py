import os
import unittest
from unittest.mock import patch

from app.utils.network import _get_test_hosts, _state, is_system_online


class TestIsSystemOnline(unittest.TestCase):
    def setUp(self):
        _state.update(
            {
                "last_online_time": None,
                "last_online_reason": None,
                "last_offline_log": None,
                "last_dns_ok_time": None,
                "last_wan_ok_time": None,
                "last_lan_ok_time": None,
                "last_dns_ok_reason": None,
                "last_wan_ok_reason": None,
                "last_lan_ok_reason": None,
            }
        )

    @patch("socket.create_connection")
    def test_first_host_success(self, mock_conn):
        mock_conn.return_value = None
        with patch.dict(
            os.environ,
            {"ONLINE_TEST_HOSTS": "1.1.1.1", "ONLINE_TEST_URLS": ""},
        ):
            self.assertTrue(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)

    @patch("socket.create_connection", side_effect=OSError)
    def test_all_hosts_fail(self, mock_conn):
        with patch.dict(
            os.environ,
            {"ONLINE_TEST_HOSTS": "1.1.1.1,2.2.2.2", "ONLINE_TEST_URLS": ""},
        ):
            self.assertFalse(is_system_online())
            self.assertEqual(mock_conn.call_count, 2)

    def test_get_test_hosts_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_test_hosts(), ["8.8.8.8", "1.1.1.1"])

    @patch("app.utils.network.socket.create_connection")
    @patch("app.utils.network._get_test_hosts", return_value=[" ", "2.2.2.2"])
    def test_is_system_online_skips_blank(self, mock_hosts, mock_conn):
        mock_conn.return_value = None
        with patch.dict(os.environ, {"ONLINE_TEST_URLS": ""}):
            self.assertTrue(is_system_online(timeout=2))
        mock_conn.assert_called_once_with(("2.2.2.2", 443), timeout=2)

    @patch("socket.create_connection")
    def test_custom_port_success(self, mock_conn):
        mock_conn.return_value = None
        with patch.dict(
            os.environ,
            {
                "ONLINE_TEST_HOSTS": "1.1.1.1",
                "ONLINE_TEST_PORT": "123",
                "ONLINE_TEST_URLS": "",
            },
        ):
            self.assertTrue(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 123), timeout=1)

    @patch("socket.create_connection", side_effect=OSError)
    def test_custom_port_failure(self, mock_conn):
        with patch.dict(
            os.environ,
            {
                "ONLINE_TEST_HOSTS": "1.1.1.1",
                "ONLINE_TEST_PORT": "321",
                "ONLINE_TEST_URLS": "",
            },
        ):
            self.assertFalse(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 321), timeout=1)

    @patch("socket.create_connection")
    def test_host_with_inline_port(self, mock_conn):
        mock_conn.return_value = None
        with patch.dict(
            os.environ,
            {"ONLINE_TEST_HOSTS": "example.com:444", "ONLINE_TEST_URLS": ""},
        ):
            self.assertTrue(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("example.com", 444), timeout=1)

    @patch("app.utils.network.probe_url_with_range")
    def test_url_success(self, mock_probe):
        mock_probe.return_value = (True, {"ok": True})
        with patch.dict(os.environ, {"ONLINE_TEST_URLS": "http://example.com"}):
            self.assertTrue(is_system_online(timeout=1))
            mock_probe.assert_called_once_with(
                "http://example.com", timeout=1, preconnect=True
            )

    @patch("socket.create_connection")
    @patch("app.utils.network.probe_url_with_range")
    def test_url_failure_falls_back_to_hosts(self, mock_probe, mock_conn):
        mock_conn.return_value = None
        mock_probe.return_value = (False, {"ok": False})
        with patch.dict(
            os.environ,
            {"ONLINE_TEST_URLS": "http://bad", "ONLINE_TEST_HOSTS": "1.1.1.1"},
        ):
            self.assertTrue(is_system_online(timeout=1))
            mock_probe.assert_called_once_with("http://bad", timeout=1, preconnect=True)
            mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)

    @patch("app.utils.network.logging.warning")
    @patch("app.utils.network.socket.create_connection", side_effect=OSError("fail"))
    def test_logs_when_all_fail(self, mock_conn, mock_warn):
        with (
            patch("app.utils.network._get_test_hosts", return_value=["1.1.1.1"]),
            patch.dict(os.environ, {"ONLINE_TEST_URLS": ""}),
        ):
            self.assertFalse(is_system_online(timeout=1))
        mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)
        mock_warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
