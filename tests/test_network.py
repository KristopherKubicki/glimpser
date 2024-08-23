import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.retention_policy import get_files_sorted_by_creation_time
from app.utils.screenshots import is_private_ip

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

if __name__ == '__main__':
    unittest.main()

