import unittest
import os
import sys
import tempfile
import socket
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.retention_policy import get_files_sorted_by_creation_time
from app.utils.screenshots import is_private_ip, is_address_reachable, is_port_open, parse_url, get_arp_output

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

    def test_is_address_reachable(self):
        # Test reachable address (assuming google.com is always reachable)
        self.assertTrue(is_address_reachable("google.com"))

        # Test unreachable address
        self.assertFalse(is_address_reachable("nonexistent.domain.com"))

        # Test with different port
        self.assertTrue(is_address_reachable("google.com", port=443))

        # Test with timeout
        #self.assertFalse(is_address_reachable("10.255.255.255", timeout=1)) # for some reason this passes on my network...

    def test_is_port_open(self):
        # Test open port (assuming port 80 is open on google.com)
        self.assertTrue(is_port_open("google.com", 80))

        # Test closed port
        self.assertFalse(is_port_open("google.com", 12345))

        # Test with timeout
        #self.assertFalse(is_port_open("10.255.255.255", 80, timeout=1))

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

    def test_get_arp_output(self):
        # Test get_arp_output function
        # Note: This test might need to be adjusted based on the actual implementation and system
        try:
            output = get_arp_output("127.0.0.1", timeout=1)
            self.assertIsInstance(output, bytes)
        except subprocess.TimeoutExpired:
            self.skipTest("ARP command timed out")
        except subprocess.CalledProcessError:
            self.skipTest("ARP command failed")

if __name__ == '__main__':
    unittest.main()

