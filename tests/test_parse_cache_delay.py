import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import app.routes as routes


class TestParseCacheDelay(unittest.TestCase):
    def test_cache_control_max_age(self):
        headers = {"Cache-Control": "public, max-age=60"}
        self.assertEqual(routes.parse_cache_delay(headers), 60)

    def test_expires_header(self):
        future = datetime.utcnow() + timedelta(seconds=30)
        headers = {"Expires": future.strftime("%a, %d %b %Y %H:%M:%S GMT")}
        ttl = routes.parse_cache_delay(headers)
        self.assertTrue(0 <= ttl <= 30)

    def test_invalid_max_age_logs(self):
        headers = {"Cache-Control": "max-age=60"}
        with patch("builtins.float", side_effect=ValueError):
            with self.assertLogs(level="WARNING") as logs:
                self.assertEqual(routes.parse_cache_delay(headers), 0.0)
        joined = "\n".join(logs.output)
        self.assertIn("Invalid max-age header", joined)

    def test_invalid_expires_logs(self):
        headers = {"Expires": "not a date"}
        with self.assertLogs(level="WARNING") as logs:
            self.assertEqual(routes.parse_cache_delay(headers), 0.0)
        joined = "\n".join(logs.output)
        self.assertIn("Invalid Expires header", joined)


if __name__ == "__main__":
    unittest.main()
