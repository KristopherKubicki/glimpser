import unittest
import tempfile
import os
import sys
import importlib.util
from datetime import datetime, timedelta

# Dynamically load the video_details module without importing the full
# ``app`` package and its heavy dependencies.
module_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "utils", "video_details.py")
)
spec = importlib.util.spec_from_file_location("video_details", module_path)
video_details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_details)

get_latest_video_date = video_details.get_latest_video_date
get_latest_screenshot_date = video_details.get_latest_screenshot_date
get_latest_file = video_details.get_latest_file
get_latest_date = video_details.get_latest_date


class TestVideoDetails(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def create_dummy_file(self, filename, days_ago=0):
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, "w") as f:
            f.write("dummy content")
        file_time = datetime.now() - timedelta(days=days_ago)
        os.utime(file_path, (file_time.timestamp(), file_time.timestamp()))

    def test_get_latest_video_date(self):
        self.create_dummy_file("video1.mp4", days_ago=2)
        self.create_dummy_file("video2.mp4", days_ago=1)
        self.create_dummy_file("video3.mp4", days_ago=3)

        latest_date = get_latest_video_date(self.temp_dir)
        expected_date = (datetime.now() - timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.assertEqual(
            latest_date[:10], expected_date[:10]
        )  # Compare only the date part

    def test_get_latest_screenshot_date(self):
        self.create_dummy_file("screenshot1.png", days_ago=2)
        self.create_dummy_file("screenshot2.png", days_ago=1)
        self.create_dummy_file("screenshot3.png", days_ago=3)

        latest_date = get_latest_screenshot_date(self.temp_dir)
        expected_date = (datetime.now() - timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.assertEqual(
            latest_date[:10], expected_date[:10]
        )  # Compare only the date part

    def test_get_latest_file(self):
        self.create_dummy_file("file1.txt", days_ago=2)
        self.create_dummy_file("file2.txt", days_ago=1)
        self.create_dummy_file("file3.txt", days_ago=3)
        latest_file = get_latest_file(self.temp_dir, ext="mp4")
        self.assertEqual(latest_file, None)

        latest_file = get_latest_file(self.temp_dir, ext="txt")
        self.assertEqual(latest_file, "file2.txt")

        self.create_dummy_file("latest_camera.png", days_ago=5)
        latest_file = get_latest_file(self.temp_dir, ext="txt")
        self.assertEqual(latest_file, "file2.txt")

        latest_file = get_latest_file(self.temp_dir, ext="png")
        expected_path = os.path.join(self.temp_dir, "latest_camera.png")
        self.assertEqual(latest_file, expected_path)

    def test_get_latest_date(self):
        """
        Tests that get_latest_date returns the most recent modification date for files with a given extension in the temporary directory.
        """
        self.create_dummy_file("file1.txt", days_ago=2)
        self.create_dummy_file("file2.txt", days_ago=1)
        self.create_dummy_file("file3.txt", days_ago=3)

        latest_date = get_latest_date(self.temp_dir, ext="txt")
        expected_date = (datetime.now() - timedelta(days=1)).date()

        # Convert latest_date to a date object for comparison
        latest_date_obj = datetime.strptime(latest_date, "%Y-%m-%d %H:%M:%S").date()

        self.assertEqual(latest_date_obj, expected_date, "The latest date does not match the expected date")

    def test_get_latest_file_empty_directory(self):
        latest_file = get_latest_file(self.temp_dir, ext="txt")
        self.assertIsNone(latest_file)

    def test_get_latest_date_empty_directory(self):
        latest_date = get_latest_date(self.temp_dir, ext="txt")
        self.assertIsNone(latest_date)


if __name__ == "__main__":
    unittest.main()
