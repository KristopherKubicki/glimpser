import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import app.utils.screenshots as ss


class TestCaptureStatusErrors(unittest.TestCase):
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

    @patch("app.utils.screenshots.is_address_reachable")
    @patch("app.utils.screenshots.download_image")
    def test_capture_skips_on_cached_error(self, mock_download, mock_reachable):
        url = "http://example.com/image.png"
        ss.set_cached_status_code(url, 403)
        result = ss.capture_or_download("test", {"url": url})
        self.assertFalse(result)
        mock_download.assert_not_called()
        mock_reachable.assert_not_called()

    @patch("app.utils.screenshots.http_session")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_get_content_type_caches_error(self, mock_online, mock_session_factory):
        url = "http://example.com"
        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        mock_session.request.return_value = resp
        mock_session_factory.return_value = mock_session

        ctype, modified = ss.get_content_type(url, False)
        self.assertEqual(ctype, "")
        self.assertFalse(modified)
        self.assertEqual(ss.get_cached_status_code(url), 500)

    @patch("app.utils.screenshots.http_session")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_get_content_type_head_403_fallback(
        self, mock_online, mock_session_factory
    ):
        url = "http://example.com"
        mock_session = MagicMock()
        head_resp = MagicMock()
        head_resp.status_code = 403
        head_resp.headers = {}
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.headers = {"Content-Type": "video/mp4"}
        mock_session.request.side_effect = [head_resp, get_resp]
        mock_session_factory.return_value = mock_session

        ctype, modified = ss.get_content_type(url, False)
        self.assertEqual(ctype, "video/mp4")
        self.assertTrue(modified)


if __name__ == "__main__":
    unittest.main()
