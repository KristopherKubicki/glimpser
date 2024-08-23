import unittest
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.video_details import get_latest_file, get_latest_date


class TestVideoDetails(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def create_test_files(self, file_names, time_offset=0):
        for i, name in enumerate(file_names):
            path = os.path.join(self.temp_dir, name)
            with open(path, "w") as f:
                f.write("test content")
            os.utime(path, (datetime.now().timestamp() + i + time_offset,) * 2)

    def test_get_latest_file(self):
        test_files = ["file1.png", "file2.png", "file3.png"]
        self.create_test_files(test_files)

        latest_file = get_latest_file(self.temp_dir, "png")
        self.assertEqual(latest_file, "file3.png")

    def test_get_latest_file_with_different_extensions(self):
        test_files = ["file1.png", "file2.jpg", "file3.png"]
        self.create_test_files(test_files)

        latest_png = get_latest_file(self.temp_dir, "png")
        self.assertEqual(latest_png, "file3.png")

        latest_jpg = get_latest_file(self.temp_dir, "jpg")
        self.assertEqual(latest_jpg, "file2.jpg")

    def test_get_latest_file_empty_directory(self):
        latest_file = get_latest_file(self.temp_dir, "png")
        self.assertIsNone(latest_file)

    def test_get_latest_date(self):
        test_files = ["file1.png", "file2.png", "file3.png"]
        self.create_test_files(test_files)

        latest_date = get_latest_date(self.temp_dir, "png")
        expected_date = datetime.fromtimestamp(
            os.path.getctime(os.path.join(self.temp_dir, "file3.png"))
        )
        self.assertEqual(latest_date, expected_date.strftime("%Y-%m-%d %H:%M:%S"))

    def test_get_latest_date_empty_directory(self):
        latest_date = get_latest_date(self.temp_dir, "png")
        self.assertIsNone(latest_date)

    def test_get_latest_date_with_symlink(self):
        test_files = ["file1.png", "file2.png", "latest_camera.png"]
        self.create_test_files(test_files)

        symlink_path = os.path.join(self.temp_dir, "latest_camera.png")
        os.symlink(os.path.join(self.temp_dir, "file2.png"), symlink_path)

        latest_date = get_latest_date(self.temp_dir, "png")
        expected_date = datetime.fromtimestamp(os.path.getctime(symlink_path))
        self.assertEqual(latest_date, expected_date.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    unittest.main()
