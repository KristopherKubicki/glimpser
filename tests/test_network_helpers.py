"""Tests for network helpers."""
import unittest
from unittest.mock import patch

from app.utils import network


class TestParseTarget(unittest.TestCase):
    def test_host_only_returns_default_port(self):
        self.assertEqual(network._parse_target("example.com", 80), ("example.com", 80))

    def test_host_with_port(self):
        self.assertEqual(
            network._parse_target("example.com:8080", 80), ("example.com", 8080)
        )

    def test_host_with_invalid_port_uses_default(self):
        self.assertEqual(
            network._parse_target("example.com:notaport", 80), ("example.com", 80)
        )

    def test_ipv6_host_with_port(self):
        self.assertEqual(
            network._parse_target("2001:db8::1:8443", 443), ("2001:db8::1", 8443)
        )


class TestTryConnect(unittest.TestCase):
    @patch("app.utils.network.socket.create_connection")
    def test_try_connect_success(self, mock_conn):
        mock_conn.return_value = None
        result = network._try_connect("host.com:443", timeout=1, default_port=80)
        self.assertTrue(result)
        mock_conn.assert_called_once_with(("host.com", 443), timeout=1)

    @patch("app.utils.network.socket.create_connection", side_effect=OSError())
    def test_try_connect_failure(self, mock_conn):
        result = network._try_connect("host.com", timeout=2, default_port=80)
        self.assertFalse(result)
        mock_conn.assert_called_once_with(("host.com", 80), timeout=2)


if __name__ == "__main__":
    unittest.main()
