import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import patch

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.retention_policy import (
    get_files_sorted_by_creation_time,
    delete_old_files,
    retention_cleanup,
)


class TestRetentionPolicy(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Remove the temporary directory after the test
        shutil.rmtree(self.test_dir)

    def test_get_files_sorted_by_creation_time(self):
        # Create some test files with different creation times
        file_names = ["file1.txt", "file2.txt", "file3.txt"]
        for i, name in enumerate(file_names):
            path = os.path.join(self.test_dir, name)
            with open(path, "w") as f:
                f.write("test content")
            os.utime(path, (os.stat(path).st_atime, os.stat(path).st_mtime + i))

        # Get sorted files
        sorted_files = get_files_sorted_by_creation_time(self.test_dir)

        # Check if files are sorted correctly
        self.assertEqual(len(sorted_files), 3)
        self.assertTrue(os.path.basename(sorted_files[0]).startswith("file1"))
        self.assertTrue(os.path.basename(sorted_files[1]).startswith("file2"))
        self.assertTrue(os.path.basename(sorted_files[2]).startswith("file3"))

    def test_delete_old_files(self):
        # Create some test files
        file_names = ["file1.txt", "file2.txt", "file3.txt", "file4.txt"]
        for name in file_names:
            path = os.path.join(self.test_dir, name)
            with open(path, "w") as f:
                f.write("test content")

        # Mock os.path.getctime to return controlled creation times
        with patch("os.path.getctime") as mock_getctime:
            mock_getctime.side_effect = [100, 200, 300, 400]

            # Call delete_old_files
            delete_old_files(
                [os.path.join(self.test_dir, f) for f in file_names],
                max_age=2,
                max_size=1000,
                minimum=2,
            )

        # Check if the correct files were deleted
        remaining_files = os.listdir(self.test_dir)
        self.assertEqual(len(remaining_files), 2)
        self.assertIn("file3.txt", remaining_files)
        self.assertIn("file4.txt", remaining_files)

    @patch("app.utils.retention_policy.os.listdir")
    @patch("app.utils.retention_policy.get_files_sorted_by_creation_time")
    @patch("app.utils.retention_policy.delete_old_files")
    def test_retention_cleanup(
        self, mock_delete_old_files, mock_get_files, mock_listdir
    ):
        # Mock the necessary functions and variables
        mock_listdir.return_value = ["camera1", "camera2"]
        mock_get_files.return_value = ["file1.mp4", "file2.mp4"]

        # Call retention_cleanup
        retention_cleanup()

        # Check if the functions were called with correct arguments
        self.assertEqual(
            mock_listdir.call_count, 2
        )  # Once for VIDEO_DIRECTORY and once for SCREENSHOT_DIRECTORY
        self.assertEqual(
            mock_get_files.call_count, 4
        )  # Twice for each camera (video and screenshot)
        self.assertEqual(
            mock_delete_old_files.call_count, 4
        )  # Twice for each camera (video and screenshot)


if __name__ == "__main__":
    unittest.main()
