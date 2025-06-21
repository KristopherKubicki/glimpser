import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import app.utils.screenshots as ss


class TestScreenshotsExtras(unittest.TestCase):
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

    def test_is_valid_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            Image.new("RGB", (1, 1)).save(tmp, format="PNG")
            tmp_path = tmp.name
        try:
            self.assertTrue(ss._is_valid_png(tmp_path))
            with open(tmp_path, "wb") as f:
                f.write(b"not a png")
            self.assertFalse(ss._is_valid_png(tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_cached_status_code(self):
        url = "http://example.com"
        ss.set_cached_status_code(url, 201)
        self.assertEqual(ss.get_cached_status_code(url), 201)
        ss.status_code_cache_time[url] -= ss.STATUS_CACHE_TTL + 1
        self.assertIsNone(ss.get_cached_status_code(url))

    def test_check_if_modified(self):
        url = "http://example.com"
        headers = {"Last-Modified": "Mon, 01 Jan 2020 00:00:00 GMT", "ETag": "abc"}
        self.assertTrue(ss.check_if_modified(url, headers))
        self.assertFalse(ss.check_if_modified(url, headers))

    def test_auth_helpers(self):
        url = "http://user:pass@example.com"  # pragma: allowlist secret
        basic = ss.get_auth(url)
        digest = ss.get_digest_auth(url)
        self.assertEqual(basic.username, "user")
        self.assertEqual(basic.password, "pass")
        self.assertEqual(digest.username, "user")
        self.assertEqual(digest.password, "pass")
        fallback = ss.get_auth("http://example.com", "u", "p")
        self.assertEqual(fallback.username, "u")
        self.assertEqual(fallback.password, "p")

    def test_url_type_helpers(self):
        self.assertTrue(ss.is_image_url("http://x/a.jpg", ""))
        self.assertTrue(ss.is_pdf_url("http://x/doc.pdf", ""))
        self.assertTrue(ss.is_video_stream_url("rtsp://cam", ""))
        self.assertFalse(ss.is_video_stream_url("http://x/image.png", "image/png"))

    def test_browser_selection(self):
        url = "http://example.com"
        with patch.object(ss, "is_enhanced", return_value=False):
            self.assertTrue(
                ss.should_use_lightweight_browser(
                    url, None, None, False, False, False, False
                )
            )
            self.assertFalse(
                ss.should_use_lightweight_browser(
                    url, None, None, True, False, False, False
                )
            )
            self.assertTrue(
                ss.should_use_phantom_browser(
                    url, None, None, False, False, False, False
                )
            )
            self.assertFalse(
                ss.should_use_phantom_browser(
                    url, None, None, False, True, False, False
                )
            )


if __name__ == "__main__":
    unittest.main()
