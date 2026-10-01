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


class TestRtspDescribeProbe(unittest.TestCase):
    def test_describe_accepts_video_with_zero_port(self):
        response = (
            "RTSP/1.0 200 OK\r\n"
            "Content-Type: application/sdp\r\n\r\n"
            "v=0\r\n"
            "m=video 0 RTP/AVP 96\r\n"
            "a=rtpmap:96 H264/90000\r\n"
        )
        with patch(
            "app.utils.screenshots._rtsp_request",
            return_value=(200, response, {"Content-Type": "application/sdp"}),
        ):
            ok, codec = ss._rtsp_describe_probe("rtsp://example.com/stream", timeout=1)
        self.assertTrue(ok)
        self.assertEqual(codec, "h264")


class TestRtspCredentials(unittest.TestCase):
    def test_percent_encoded_password_is_decoded(self):
        user, pwd = ss._rtsp_credentials("rtsp://admin:pn%21hDF8gB%40J1@example/stream")
        self.assertEqual(user, "admin")
        self.assertEqual(pwd, "pn!hDF8gB@J1")


class TestRedirectLoopDetection(unittest.TestCase):
    def test_auth_history_does_not_count_as_redirect_loop(self):
        class Resp:
            def __init__(self, url, status_code):
                self.url = url
                self.status_code = status_code

        self.assertFalse(
            ss._is_redirect_loop([Resp("http://cam/", 401)], "http://cam/")
        )

    def test_redirect_loop_marker_only(self):
        ss.redirect_loop_cache.clear()
        ss.redirect_loop_cache_time.clear()
        url = "http://cam/"
        ss.redirect_loop_cache[url] = {"fingerprint": "x", "count": 1}
        ss.redirect_loop_cache_time[url] = ss.time.time()
        self.assertFalse(ss._has_redirect_loop(url))
        ss.redirect_loop_cache[url] = "redirect_loop"
        self.assertTrue(ss._has_redirect_loop(url))


if __name__ == "__main__":
    unittest.main()
