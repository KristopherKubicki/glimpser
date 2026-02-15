import unittest

from app import routes


class TestLiveStreamUrlResolution(unittest.TestCase):
    def test_rtsp_keeps_main_profile_channel(self):
        details = {
            "url": "rtsp://admin:pass@cam.local:8554/Streaming/Channels/102?foo=1",
        }
        out = routes.resolve_live_stream_url(details, profile="main")
        self.assertIn("/Streaming/Channels/101", out)

    def test_rtsp_switches_to_sub_profile_channel(self):
        details = {
            "url": "rtsp://admin:pass@cam.local/Streaming/Channels/101",
        }
        out = routes.resolve_live_stream_url(details, profile="sub")
        self.assertIn("/Streaming/Channels/102", out)

    def test_http_hikvision_picture_converts_to_rtsp(self):
        details = {
            "url": "http://admin:pass@192.168.1.57/ISAPI/Streaming/channels/101/picture",
        }
        out = routes.resolve_live_stream_url(details, profile="main")
        self.assertTrue(out.startswith("rtsp://"))
        self.assertIn("/Streaming/Channels/101", out)
        self.assertIn("transportmode=unicast", out)

    def test_non_stream_url_returns_none(self):
        details = {"url": "https://example.com"}
        self.assertIsNone(routes.resolve_live_stream_url(details, profile="main"))


if __name__ == "__main__":
    unittest.main()
