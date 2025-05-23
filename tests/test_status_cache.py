import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.screenshots import (
    set_cached_status_code,
    get_cached_status_code,
    status_code_cache,
    status_code_cache_time,
    STATUS_CACHE_TTL,
)


class TestStatusCodeCache(unittest.TestCase):
    def setUp(self):
        status_code_cache.clear()
        status_code_cache_time.clear()

    def test_cache_expiry_and_cleanup(self):
        with patch("time.time") as mock_time:
            # Store code at deterministic timestamp
            mock_time.return_value = 100
            set_cached_status_code("u", 200)

            self.assertEqual(status_code_cache["u"], 200)
            self.assertEqual(status_code_cache_time["u"], 100)

            # Retrieve before expiration
            mock_time.return_value = 100 + STATUS_CACHE_TTL - 1
            self.assertEqual(get_cached_status_code("u"), 200)
            self.assertIn("u", status_code_cache)
            self.assertIn("u", status_code_cache_time)

            # Advance time past TTL and verify cleanup
            mock_time.return_value = 100 + STATUS_CACHE_TTL + 1
            self.assertIsNone(get_cached_status_code("u"))
            self.assertEqual(status_code_cache, {})
            self.assertEqual(status_code_cache_time, {})


if __name__ == "__main__":
    unittest.main()
