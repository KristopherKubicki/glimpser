import unittest
from datetime import datetime, timedelta

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


if __name__ == "__main__":
    unittest.main()
