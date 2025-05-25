import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.routes import allowed_filename

class TestAllowedFilename(unittest.TestCase):
    def test_valid(self):
        valid = ['image.png', 'file-1.txt', 'archive.tar.gz', 'simple']
        for name in valid:
            with self.subTest(name=name):
                self.assertTrue(allowed_filename(name))

    def test_invalid(self):
        invalid = ['../secret', 'bad/name', 'name space', 'weird\x00char', '']
        for name in invalid:
            with self.subTest(name=name):
                self.assertFalse(allowed_filename(name))

if __name__ == '__main__':
    unittest.main()
