import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.template_manager import is_snapshot_url


class TestIsSnapshotUrl(unittest.TestCase):
    def test_detects_snapshot_endpoints(self):
        self.assertTrue(is_snapshot_url("http://cam/snapshot.jpg"))
        self.assertTrue(is_snapshot_url("http://cam/picture"))
        self.assertTrue(is_snapshot_url("http://cam/foo.SNAPSHOT"))

    def test_non_snapshot_urls(self):
        self.assertFalse(is_snapshot_url("http://cam/stream.m3u8"))
        self.assertFalse(is_snapshot_url(""))


if __name__ == "__main__":
    unittest.main()
