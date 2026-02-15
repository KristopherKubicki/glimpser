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
    def test_get_content_type_get_probe_content_type(
        self, mock_state, mock_online, mock_session_factory
    ):
        url = "http://example.com"
        mock_session = MagicMock()
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.headers = {"Content-Type": "video/mp4"}
        get_resp.history = []
        get_resp.url = url
        mock_session.request.side_effect = [get_resp]
        mock_session_factory.return_value = mock_session

        ctype, modified, preflight_ok, reason = ss.get_content_type(url, False)
        self.assertEqual(ctype, "video/mp4")
        self.assertTrue(modified)
        self.assertTrue(preflight_ok)
        self.assertEqual(reason, "ok")

    @patch("app.utils.screenshots.http_session")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch(
        "app.utils.screenshots.network_state",
        return_value={"dns_ok": True, "wan_ok": True, "lan_ok": True},
    )
    def test_get_content_type_ignores_https_redirect_pin_for_lan_http(
        self, _mock_state, _mock_online, mock_session_factory
    ):
        url = "http://192.168.1.66/ISAPI/Streaming/channels/101/picture"
        ss.redirect_pin_cache[url] = (
            "https://192.168.1.66/ISAPI/Streaming/channels/101/picture"
        )
        ss.redirect_pin_cache_time[url] = 9999999999

        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        resp.history = []
        resp.url = url
        resp.cookies = None
        resp.raw = MagicMock()
        resp.raw.read.return_value = b"\xff\xd8\xff" * 1000
        mock_session.request.return_value = resp
        mock_session_factory.return_value = mock_session

        ctype, _modified, preflight_ok, _reason = ss.get_content_type(url, False)
        self.assertTrue(preflight_ok)
        self.assertEqual(ctype, "image/jpeg")
        # Ensure we didn't follow the https pin for a private host.
        called_url = mock_session.request.call_args[0][1]
        self.assertEqual(called_url, url)

    @patch("app.utils.screenshots.http_session")
    @patch("app.utils.screenshots.is_system_online", return_value=True)
    @patch(
        "app.utils.screenshots.network_state",
        return_value={"dns_ok": True, "wan_ok": True, "lan_ok": True},
    )
    @patch("app.utils.screenshots.config.LOW_CPU_MODE", True)
    @patch("app.utils.screenshots.PREFLIGHT_LOW_CPU_WAN_BUDGET_SECONDS", 2)
    def test_get_content_type_uses_low_cpu_timeout_budget(
        self,
        _mock_state,
        _mock_online,
        mock_session_factory,
    ):
        url = "http://example.com/snapshot.jpg"
        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        resp.history = []
        resp.url = url
        resp.cookies = None
        resp.raw = MagicMock()
        resp.raw.read.return_value = b"\xff\xd8\xff" * 1000
        mock_session.request.return_value = resp
        mock_session_factory.return_value = mock_session

        _ctype, _modified, preflight_ok, _reason = ss.get_content_type(url, False)

        self.assertTrue(preflight_ok)
        self.assertLessEqual(mock_session.request.call_args.kwargs["timeout"], 2)

    @patch("app.utils.screenshots._record_tier_failure")
    @patch("app.utils.screenshots.record_preflight_backoff")
    @patch("app.utils.screenshots.network_state", return_value={"lan_ok": True})
    @patch("app.utils.screenshots._local_quarantine_active", return_value=(False, 0))
    @patch("app.utils.screenshots._get_auth_hint", return_value=False)
    @patch("app.utils.screenshots.is_address_reachable", return_value=False)
    def test_lan_fast_probe_blocks_unreachable_local_host(
        self,
        mock_reachable,
        _auth_hint,
        _quarantine,
        _net_state,
        mock_backoff,
        mock_tier_failure,
    ):
        url = "http://192.168.1.66/ISAPI/Streaming/channels/101/picture"
        result = ss._capture_or_download_inner(
            "cam",
            {"timeout": 30},
            url,
            url,
            None,
            None,
        )

        self.assertFalse(result)
        self.assertTrue(mock_reachable.called)
        self.assertEqual(mock_reachable.call_args.kwargs.get("port"), 80)
        self.assertEqual(
            mock_reachable.call_args.kwargs.get("timeout"),
            ss.PREFLIGHT_LAN_FAST_PROBE_TIMEOUT,
        )
        mock_backoff.assert_called_once()
        mock_tier_failure.assert_called_once()

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
