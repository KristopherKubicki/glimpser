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
        ss.throttle_cache.clear()
        ss.source_circuit_cache.clear()
        ss.domain_retry_budget_cache.clear()
        ss._persist_status_cache()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch(
        "app.utils.screenshots.network_state",
        return_value={"dns_ok": True, "wan_ok": True, "lan_ok": True},
    )
    @patch("app.utils.screenshots.is_address_reachable")
    @patch("app.utils.screenshots.download_image")
    def test_capture_skips_on_cached_error(
        self, mock_download, mock_reachable, _mock_state
    ):
        url = "http://example.com/image.png"
        ss.set_cached_status_code(url, 403)
        result = ss.capture_or_download("test", {"url": url})
        self.assertFalse(result)
        mock_download.assert_not_called()
        mock_reachable.assert_not_called()

    @patch(
        "app.utils.screenshots.network_state",
        return_value={"dns_ok": True, "wan_ok": True, "lan_ok": True},
    )
    @patch("app.utils.screenshots.http_session")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    def test_get_content_type_caches_error(
        self, mock_online, mock_session_factory, _mock_state
    ):
        url = "http://example.com"
        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        mock_session.request.return_value = resp
        mock_session_factory.return_value = mock_session

        ctype, modified, preflight_ok, reason = ss.get_content_type(url, False)
        self.assertEqual(ctype, "")
        self.assertFalse(modified)
        self.assertFalse(preflight_ok)
        self.assertEqual(reason, "http_500")
        self.assertEqual(ss.get_cached_status_code(url), 500)

    @patch("app.utils.screenshots.http_session")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch("app.utils.screenshots.network_state", return_value={"dns_ok": True})
    def test_get_content_type_head_403_fallback(
        self, mock_state, mock_online, mock_session_factory
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

        ctype, modified, preflight_ok, reason = ss.get_content_type(url, False)
        self.assertEqual(ctype, "video/mp4")
        self.assertTrue(modified)
        self.assertTrue(preflight_ok)
        self.assertEqual(reason, "ok")

    @patch("app.utils.screenshots.network_state")
    @patch("app.utils.screenshots._capture_or_download_inner")
    def test_capture_pauses_external_when_wan_or_dns_offline(
        self, mock_inner, mock_network_state
    ):
        url = "http://example.com/image.png"
        mock_network_state.return_value = {"dns_ok": False, "wan_ok": False}

        result = ss.capture_or_download("test", {"url": url})

        self.assertFalse(result)
        mock_inner.assert_not_called()
        entry = ss.throttle_cache.get(url, {})
        self.assertEqual(entry.get("reason"), "dns_offline")
        self.assertGreater(entry.get("timeout", 0), 0)

    @patch("app.utils.screenshots.network_state")
    @patch("app.utils.screenshots._release_domain")
    @patch("app.utils.screenshots._try_acquire_domain", return_value=True)
    @patch("app.utils.screenshots._capture_or_download_inner", return_value=True)
    def test_capture_allows_lan_hostname_when_wan_offline(
        self,
        mock_inner,
        _mock_acquire,
        _mock_release,
        mock_network_state,
    ):
        url = "http://camera.lan/snapshot.jpg"
        mock_network_state.return_value = {"dns_ok": False, "wan_ok": False}

        result = ss.capture_or_download("cam", {"url": url})

        self.assertTrue(result)
        mock_inner.assert_called_once()

    @patch(
        "app.utils.screenshots.network_state",
        return_value={"dns_ok": True, "wan_ok": True, "lan_ok": True},
    )
    @patch("app.utils.screenshots._capture_or_download_inner")
    def test_source_circuit_open_skips_capture(self, mock_inner, _mock_state):
        url = "http://example.com/image.png"
        ss.source_circuit_cache[url.lower()] = {
            "open_until": ss.time.time() + 60,
            "count": 99,
            "window_start": ss.time.time(),
        }

        result = ss.capture_or_download("test", {"url": url})

        self.assertFalse(result)
        mock_inner.assert_not_called()

    @patch(
        "app.utils.screenshots.network_state",
        return_value={"dns_ok": True, "wan_ok": True, "lan_ok": True},
    )
    @patch("app.utils.screenshots._capture_or_download_inner")
    def test_retry_budget_exhausted_blocks_capture(self, mock_inner, _mock_state):
        url = "http://example.com/image.png"
        key = "example.com"
        ss.domain_retry_budget_cache[key] = {
            "count": ss.DOMAIN_RETRY_BUDGET_LIMIT,
            "window_start": ss.time.time(),
            "blocked_until": 0,
        }

        result = ss.capture_or_download("test", {"url": url})

        self.assertFalse(result)
        mock_inner.assert_not_called()
        entry = ss.throttle_cache.get(url, {})
        self.assertEqual(entry.get("reason"), "retry_budget_exhausted")


if __name__ == "__main__":
    unittest.main()
