# tests/test_network.py

import tempfile
import unittest
from unittest.mock import patch

from app.utils.chrome_utils import is_port_open
from app.utils.retention_policy import get_files_sorted_by_creation_time
from app.utils.screenshots import (
    get_arp_output,
    is_address_reachable,
    is_private_ip,
    parse_url,
)


class TestUtils(unittest.TestCase):

    def test_get_files_sorted_by_creation_time_empty(self):
        # Test an empty directory
        with tempfile.TemporaryDirectory() as temp_dir:
            result = get_files_sorted_by_creation_time(temp_dir)
            self.assertEqual(result, [])

    def test_is_private_ip(self):
        # Test various IPs
        self.assertTrue(is_private_ip("192.168.1.1"))
        self.assertTrue(is_private_ip("10.0.0.1"))
        self.assertTrue(is_private_ip("172.16.0.1"))
        self.assertFalse(is_private_ip("8.8.8.8"))
        self.assertFalse(is_private_ip("1.1.1.1"))

    @patch("socket.gethostbyname")
    @patch("socket.socket")
    def test_is_address_reachable(self, mock_socket, mock_gethostbyname):
        # Simulate DNS resolution success, failure, and success
        mock_gethostbyname.side_effect = [
            "1.1.1.1",
            Exception("fail"),
            "1.1.1.1",
            "10.255.255.255",
        ]
        mock_instance = mock_socket.return_value
        mock_instance.connect_ex.side_effect = [0, 0, 1]

        self.assertTrue(is_address_reachable("google.com"))
        self.assertFalse(is_address_reachable("nonexistent.domain.com"))
        self.assertTrue(is_address_reachable("google.com", port=443))
        self.assertFalse(is_address_reachable("10.255.255.255", timeout=1))

    @patch("socket.socket")
    def test_is_port_open(self, mock_socket):
        mock_instance = mock_socket.return_value.__enter__.return_value
        mock_instance.connect.side_effect = [None, TimeoutError(), TimeoutError()]

        self.assertTrue(is_port_open("google.com", 80))
        self.assertFalse(is_port_open("google.com", 12345))
        self.assertFalse(is_port_open("10.255.255.255", 80, timeout=1))

    def test_parse_url(self):
        # Test parsing HTTP URL
        domain, port = parse_url("http://example.com")
        self.assertEqual(domain, "example.com")
        self.assertEqual(port, 80)

        # Test parsing HTTPS URL
        domain, port = parse_url("https://example.com:8443")
        self.assertEqual(domain, "example.com")
        self.assertEqual(port, 8443)

        # Test parsing URL without scheme
        domain, port = parse_url("example.com")
        self.assertEqual(domain, "example.com")
        self.assertIsNone(port)

        # Test parsing URL with IPv6 address
        domain, port = parse_url("http://[2001:db8::1]:8080")
        self.assertEqual(domain, "2001:db8::1")
        self.assertEqual(port, 8080)

    @patch("subprocess.check_output")
    def test_get_arp_output(self, mock_check_output):
        mock_check_output.return_value = b"REACHABLE"
        output = get_arp_output("127.0.0.1", timeout=1)
        self.assertIsInstance(output, bytes)


if __name__ == "__main__":
    unittest.main()
