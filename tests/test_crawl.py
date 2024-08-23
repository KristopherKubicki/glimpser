import unittest
import socket
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.screenshots import parse_url, is_address_reachable, get_arp_output

class TestURLParsing(unittest.TestCase):

    def test_parse_url_http(self):
        url = "http://example.com:8080/some/path"
        domain, port = parse_url(url)
        self.assertEqual(domain, "example.com")
        self.assertEqual(port, 8080)

    def test_parse_url_https(self):
        url = "https://secure.example.com/another/path"
        domain, port = parse_url(url)
        self.assertEqual(domain, "secure.example.com")
        self.assertEqual(port, 443)

    def test_parse_url_no_scheme(self):
        url = "example.com/some/path"
        domain, port = parse_url(url)
        self.assertEqual(domain, "example.com")
        self.assertIsNone(port)

class TestARPTable(unittest.TestCase):

    @patch('subprocess.check_output')
    def test_get_arp_output_linux(self, mock_check_output):
        mock_check_output.return_value = b'192.168.0.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE'
        ip_address = "192.168.0.1"
        result = get_arp_output(ip_address, timeout=5)
        self.assertIn(b'REACHABLE', result)

    @patch('subprocess.check_output')
    def test_get_arp_output_windows(self, mock_check_output):
        mock_check_output.return_value = b'Internet Address      Physical Address      Type\n192.168.0.1          00-11-22-33-44-55     dynamic'
        ip_address = "192.168.0.1"
        result = get_arp_output(ip_address, timeout=5)
        self.assertIn(b'dynamic', result)

class TestIPAddressValidation(unittest.TestCase):

    @patch('socket.gethostbyname')
    def test_is_address_reachable_success(self, mock_gethostbyname):
        mock_gethostbyname.return_value = "93.184.216.34"  # example.com IP
        with patch('socket.socket') as mock_socket:
            mock_instance = mock_socket.return_value
            mock_instance.connect_ex.return_value = 0  # Simulate successful connection
            result = is_address_reachable("example.com", port=80)
            self.assertTrue(result)

    @patch('socket.gethostbyname')
    def test_is_address_reachable_fail(self, mock_gethostbyname):
        mock_gethostbyname.return_value = "93.184.216.34"
        with patch('socket.socket') as mock_socket:
            mock_instance = mock_socket.return_value
            mock_instance.connect_ex.return_value = 1  # Simulate failed connection
            result = is_address_reachable("example.com", port=80)
            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()

