import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.utils import screenshots as ss
from app.utils import status_cache as sc


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


class TestStatusCachePersistenceNoDirectory(unittest.TestCase):
    def test_persist_status_cache_without_directory_component(self):
        original_cache = sc.status_code_cache.copy()
        original_time_cache = sc.status_code_cache_time.copy()
        original_cwd = os.getcwd()

        sc.status_code_cache.clear()
        sc.status_code_cache_time.clear()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                try:
                    with patch("app.utils.status_cache.STATUS_CACHE_PATH", "cache.json"):
                        sc.status_code_cache["example"] = 201
                        sc.status_code_cache_time["example"] = 123.0
                        sc._persist_status_cache()
                        with open("cache.json") as cache_file:
                            data = json.load(cache_file)
                    self.assertEqual(data["example"]["code"], 201)
                finally:
                    os.chdir(original_cwd)
        finally:
            sc.status_code_cache.clear()
            sc.status_code_cache.update(original_cache)
            sc.status_code_cache_time.clear()
            sc.status_code_cache_time.update(original_time_cache)


if __name__ == "__main__":
    unittest.main()
