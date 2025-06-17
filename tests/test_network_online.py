import os
import socket
import sys
import unittest
from unittest.mock import patch

import psutil

from app.utils.network import _get_test_hosts, is_system_online


class TestIsSystemOnline(unittest.TestCase):
    @patch("socket.create_connection")
    def test_first_host_success(self, mock_conn):
        mock_conn.return_value = None
        with patch.dict(os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1"}):
            self.assertTrue(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)

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
        mock_conn.assert_called_once_with(("2.2.2.2", 443), timeout=2)

    @patch("socket.create_connection")
    def test_custom_port_success(self, mock_conn):
        mock_conn.return_value = None
        with patch.dict(
            os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1", "ONLINE_TEST_PORT": "123"}
        ):
            self.assertTrue(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 123), timeout=1)

    @patch("socket.create_connection", side_effect=OSError)
    def test_custom_port_failure(self, mock_conn):
        with patch.dict(
            os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1", "ONLINE_TEST_PORT": "321"}
        ):
            self.assertFalse(is_system_online(timeout=1))
            mock_conn.assert_called_once_with(("1.1.1.1", 321), timeout=1)

    @patch("app.utils.network.logging.warning")
    @patch("app.utils.network.socket.create_connection", side_effect=OSError("fail"))
    def test_logs_when_all_fail(self, mock_conn, mock_warn):
        with patch("app.utils.network._get_test_hosts", return_value=["1.1.1.1"]):
            self.assertFalse(is_system_online(timeout=1))
        mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)
        mock_warn.assert_called_once()

    @patch("app.utils.network.logging.info")
    @patch("app.utils.network.psutil.net_if_addrs")
    @patch("app.utils.network.psutil.net_if_stats")
    @patch("app.utils.network.socket.create_connection", side_effect=OSError)
    def test_lan_fallback(self, mock_conn, mock_stats, mock_addrs, mock_info):
        snicstats = psutil._common.snicstats(
            isup=True, duplex=0, speed=0, mtu=1500, flags=0
        )
        snicaddr = psutil._common.snicaddr(
            family=socket.AF_INET,
            address="192.168.1.5",
            netmask="255.255.255.0",
            broadcast="192.168.1.255",
            ptp=None,
        )
        mock_stats.return_value = {"eth0": snicstats}
        mock_addrs.return_value = {"eth0": [snicaddr]}
        with patch.dict(os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1"}):
            self.assertTrue(is_system_online(timeout=1))
        mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)
        mock_info.assert_called_once()

    @patch("app.utils.network.psutil.net_if_addrs", return_value={})
    @patch("app.utils.network.psutil.net_if_stats", return_value={})
    @patch("app.utils.network.socket.create_connection", side_effect=OSError)
    def test_offline_without_interfaces(self, mock_conn, mock_stats, mock_addrs):
        with patch.dict(os.environ, {"ONLINE_TEST_HOSTS": "1.1.1.1"}):
            self.assertFalse(is_system_online(timeout=1))
        mock_conn.assert_called_once_with(("1.1.1.1", 443), timeout=1)


if __name__ == "__main__":
    unittest.main()
