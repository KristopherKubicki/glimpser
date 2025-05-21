# tests/retention_policy.py

import unittest
import tempfile
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch

from app.utils.retention_policy import (
    delete_old_files,
    get_files_sorted_by_creation_time,
    retention_cleanup,
)

class TestRetentionPolicy(unittest.TestCase):

    def test_delete_old_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy files with different ages
            for i in range(5):
                file_path = os.path.join(temp_dir, f"file{i}.txt")
                with open(file_path, 'w') as f:
                    f.write("Some content")
                os.utime(file_path, (i * 1000, i * 1000))  # Modify file creation time
            
            # Run the delete function
            files = os.listdir(temp_dir)
            delete_old_files([os.path.join(temp_dir, f) for f in files], max_age=0, max_size=0, minimum=2)
            
            # Check that only two files remain
            remaining_files = os.listdir(temp_dir)
            self.assertEqual(len(remaining_files), 2)

    def test_get_files_sorted_by_creation_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            files = []
            for i in range(3):
                path = os.path.join(temp_dir, f"file{i}.txt")
                with open(path, "w"):
                    pass
                os.utime(path, (100 + i, 100 + i))
                files.append(path)

            result = get_files_sorted_by_creation_time(temp_dir)
            self.assertEqual(result, files)

    @patch("app.utils.retention_policy.delete_old_files")
    @patch("app.utils.retention_policy.get_files_sorted_by_creation_time", return_value=["a", "b"])
    @patch("app.utils.retention_policy.os.listdir")
    def test_retention_cleanup(self, mock_listdir, mock_get_files, mock_delete):
        mock_listdir.side_effect = [["cam"], ["cam"]]
        with tempfile.TemporaryDirectory() as vdir, tempfile.TemporaryDirectory() as sdir:
            with patch("app.utils.retention_policy.VIDEO_DIRECTORY", vdir), patch(
                "app.utils.retention_policy.SCREENSHOT_DIRECTORY", sdir
            ):
                retention_cleanup()

        self.assertEqual(mock_get_files.call_count, 2)
        self.assertEqual(mock_delete.call_count, 2)

if __name__ == '__main__':
    unittest.main()

