import unittest
from unittest.mock import patch

from app.utils import screenshots as ss


class TestRtspPreflightBackoff(unittest.TestCase):
    def test_rtsp_preflight_backoff_threshold(self):
        url = "rtsp://example.com/stream"
        with (
            patch("app.utils.screenshots.time.time", return_value=1000.0),
            patch("app.utils.screenshots.throttle_cache", {}),
            patch("app.utils.screenshots.RTSP_PREFLIGHT_FAIL_THRESHOLD", 2),
            patch("app.utils.screenshots.RTSP_PREFLIGHT_FAIL_WINDOW_SECONDS", 60),
            patch("app.utils.screenshots.RTSP_PREFLIGHT_BACKOFF_SECONDS", 120),
        ):
            self.assertFalse(ss._record_rtsp_preflight_failure(url, "options_failed"))
            self.assertTrue(ss._record_rtsp_preflight_failure(url, "options_failed"))
            entry = ss.throttle_cache[url]
            self.assertGreaterEqual(entry.get("timeout", 0), 1120.0)


if __name__ == "__main__":
    unittest.main()
