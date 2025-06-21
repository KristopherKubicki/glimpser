import os
import tempfile
import unittest
from unittest.mock import patch


class TestDirectoryManagement(unittest.TestCase):

    def test_directory_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = os.path.join(temp_dir, "subdir")
            os.mkdir(new_dir)
            self.assertTrue(os.path.exists(new_dir))

    def test_directory_removal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = os.path.join(temp_dir, "subdir")
            os.mkdir(new_dir)
            os.rmdir(new_dir)
            self.assertFalse(os.path.exists(new_dir))

    @patch("os.makedirs")
    def test_makedirs(self, mock_makedirs):
        path = "/fake/directory"
        os.makedirs(path)
        mock_makedirs.assert_called_once_with(path)
