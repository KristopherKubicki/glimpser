import unittest
import tempfile
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.screenshots import (
    capture_screenshot_and_har,
    capture_screenshot_and_har_light,
)


class TestScreenshots(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_url = "https://example.com"
        self.output_path = os.path.join(self.temp_dir, "test_screenshot.png")

    def tearDown(self):
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        os.rmdir(self.temp_dir)

    def test_capture_screenshot_and_har(self):
        result = capture_screenshot_and_har(self.test_url, self.output_path)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.output_path))

    def test_capture_screenshot_and_har_light(self):
        result = capture_screenshot_and_har_light(self.test_url, self.output_path)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.output_path))

    def test_capture_screenshot_invalid_url(self):
        invalid_url = "https://invalidurl.example"
        result = capture_screenshot_and_har(invalid_url, self.output_path)
        self.assertFalse(result)
        self.assertFalse(os.path.exists(self.output_path))


if __name__ == "__main__":
    unittest.main()
