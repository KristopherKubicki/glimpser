import unittest
import os
import sys
import tempfile
from datetime import datetime

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.video_details import (
    get_latest_video_date,
    get_latest_screenshot_date,
    get_latest_file,
    get_latest_date,
)


class TestVideoDetails(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_get_latest_file(self):
        # Create some test files
        file1 = os.path.join(self.temp_dir, "file1.mp4")
        file2 = os.path.join(self.temp_dir, "file2.mp4")
        file3 = os.path.join(self.temp_dir, "file3.png")

        # Create files with different timestamps
        open(file1, "w").close()
        os.utime(file1, (os.path.getctime(file1), os.path.getctime(file1)))

        open(file2, "w").close()
        os.utime(file2, (os.path.getctime(file2) + 1, os.path.getctime(file2) + 1))

        open(file3, "w").close()
        os.utime(file3, (os.path.getctime(file3) + 2, os.path.getctime(file3) + 2))

        # Test get_latest_file for mp4
        self.assertEqual(get_latest_file(self.temp_dir, "mp4"), "file2.mp4")

        # Test get_latest_file for png
        self.assertEqual(get_latest_file(self.temp_dir, "png"), "file3.png")

    def test_get_latest_date(self):
        # Create a test file
        test_file = os.path.join(self.temp_dir, "test.mp4")
        open(test_file, "w").close()

        # Set a specific timestamp
        timestamp = datetime(2023, 5, 1, 12, 0, 0).timestamp()
        os.utime(test_file, (timestamp, timestamp))

        # Test get_latest_date
        expected_date = "2023-05-01 12:00:00"
        self.assertEqual(get_latest_date(self.temp_dir, "mp4"), expected_date)

    def test_get_latest_video_date(self):
        # Create a test video file
        test_file = os.path.join(self.temp_dir, "test_video.mp4")
        open(test_file, "w").close()

        # Set a specific timestamp
        timestamp = datetime(2023, 5, 1, 12, 0, 0).timestamp()
        os.utime(test_file, (timestamp, timestamp))

        # Test get_latest_video_date
        expected_date = "2023-05-01 12:00:00"
        self.assertEqual(get_latest_video_date(self.temp_dir), expected_date)

    def test_get_latest_screenshot_date(self):
        # Create a test screenshot file
        test_file = os.path.join(self.temp_dir, "test_screenshot.png")
        open(test_file, "w").close()

        # Set a specific timestamp
        timestamp = datetime(2023, 5, 1, 12, 0, 0).timestamp()
        os.utime(test_file, (timestamp, timestamp))

        # Test get_latest_screenshot_date
        expected_date = "2023-05-01 12:00:00"
        self.assertEqual(get_latest_screenshot_date(self.temp_dir), expected_date)


if __name__ == "__main__":
    unittest.main()
