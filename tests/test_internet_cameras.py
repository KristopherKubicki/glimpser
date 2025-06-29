"""Tests for internet cameras."""
import unittest

from app.utils.internet_cameras import INTERNET_CAMERAS


class TestInternetCameras(unittest.TestCase):
    def test_unique_ids(self):
        ids = [cam["id"] for cam in INTERNET_CAMERAS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_fields_and_values(self):
        required = {"id", "name", "url", "refresh_sec", "category"}
        for cam in INTERNET_CAMERAS:
            self.assertTrue(required <= cam.keys())
            self.assertIsInstance(cam["refresh_sec"], int)
            self.assertGreater(cam["refresh_sec"], 0)
            self.assertTrue(cam["url"].startswith(("http://", "https://")))

    def test_has_multiple_categories(self):
        categories = {cam["category"] for cam in INTERNET_CAMERAS}
        self.assertGreaterEqual(len(categories), 5)


if __name__ == "__main__":
    unittest.main()
