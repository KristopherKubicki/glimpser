import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import screenshots as ss


class TestStatusCodeCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.patcher = patch(
            "app.utils.screenshots.STATUS_CACHE_PATH",
            os.path.join(self.tmpdir, "cache.json"),
        )
        self.patcher.start()
        ss.status_code_cache.clear()
        ss.status_code_cache_time.clear()
        ss._persist_status_cache()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cache_expiry_and_cleanup(self):
        with patch("time.time") as mock_time:
            # Store code at deterministic timestamp
            mock_time.return_value = 100
            ss.set_cached_status_code("u", 200)

            self.assertEqual(ss.status_code_cache["u"], 200)
            self.assertEqual(ss.status_code_cache_time["u"], 100)

            # Retrieve before expiration
            mock_time.return_value = 100 + ss.STATUS_CACHE_TTL - 1
            self.assertEqual(ss.get_cached_status_code("u"), 200)
            self.assertIn("u", ss.status_code_cache)
            self.assertIn("u", ss.status_code_cache_time)

            # Advance time past TTL and verify cleanup
            mock_time.return_value = 100 + ss.STATUS_CACHE_TTL + 1
            self.assertIsNone(ss.get_cached_status_code("u"))
            self.assertEqual(ss.status_code_cache, {})
            self.assertEqual(ss.status_code_cache_time, {})

    def test_cache_persistence(self):
        ss.set_cached_status_code("u", 500)
        self.assertTrue(os.path.exists(ss.STATUS_CACHE_PATH))
        # Clear memory and reload
        ss.status_code_cache.clear()
        ss.status_code_cache_time.clear()
        ss._load_status_cache()
        self.assertEqual(ss.get_cached_status_code("u"), 500)


if __name__ == "__main__":
    unittest.main()
