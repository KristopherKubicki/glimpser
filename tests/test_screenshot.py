import unittest
import os
from utils.screenshots import capture_screenshot

class TestScreenshotCapture(unittest.TestCase):
    def setUp(self):
        self.test_url = "https://www.example.com"
        self.output_path = "test_screenshot.png"

    def test_screenshot_capture(self):
        """Test if screenshot is captured and saved correctly."""
        capture_screenshot(self.test_url, self.output_path)
        self.assertTrue(os.path.isfile(self.output_path))

    def tearDown(self):
        """Clean up after the test."""
        if os.path.isfile(self.output_path):
            os.remove(self.output_path)

if __name__ == '__main__':
    unittest.main()

