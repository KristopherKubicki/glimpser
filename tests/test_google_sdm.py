import datetime
import unittest
from unittest import mock

import requests

from app.utils import google_sdm


class TestGoogleSdm(unittest.TestCase):
    def setUp(self):
        google_sdm.clear_cached_tokens()

    def test_request_with_retries_recovers_from_transient_connection_error(self):
        response = mock.Mock(status_code=200)
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            if len(calls) == 1:
                raise requests.ConnectionError("dns blip")
            return response

        with mock.patch.object(
            google_sdm.requests, "request", side_effect=fake_request
        ):
            with mock.patch.object(google_sdm.time, "sleep") as sleep_mock:
                out = google_sdm._request_with_retries(
                    "get", "https://example.invalid/test", timeout=5
                )

        self.assertIs(out, response)
        self.assertEqual(len(calls), 2)
        sleep_mock.assert_called_once()

    def test_access_token_reuses_valid_cached_token_when_refresh_fails(self):
        expires_at = google_sdm._now_utc() + datetime.timedelta(seconds=20)
        google_sdm._access_token["default"] = "cached-token"
        google_sdm._access_expires_at["default"] = expires_at

        with mock.patch.object(
            google_sdm,
            "_refresh_access_token",
            side_effect=google_sdm.GoogleSdmError("temporary dns failure"),
        ):
            token = google_sdm.access_token()

        self.assertEqual(token, "cached-token")

    def test_resolve_sdm_to_rtsp_reuses_cached_stream_when_refresh_fails(self):
        stable_url = "sdm://example-home/device-1"
        cached = google_sdm.SdmRtspStream(
            rtsp_url="rtsps://cached.example/live",
            expires_at=google_sdm._now_utc() + datetime.timedelta(seconds=25),
        )
        google_sdm._resolved_rtsp_cache[stable_url] = cached

        with mock.patch.object(
            google_sdm,
            "_profile",
            return_value=mock.Mock(project_id="project-1"),
        ):
            with mock.patch.object(
                google_sdm,
                "generate_rtsp_stream",
                side_effect=google_sdm.GoogleSdmError("temporary oauth failure"),
            ):
                resolved = google_sdm.resolve_sdm_to_rtsp(stable_url)

        self.assertEqual(resolved, cached.rtsp_url)

    def test_stable_key_for_webrtc_preview_url_extracts_device(self):
        preview_url = (
            "https://127.0.0.1:8443/integrations/google/webrtc/preview"
            "?profile=example-home&device_id=device-1&token=abc"
        )

        stable = google_sdm.stable_key_for_webrtc_preview_url(preview_url)

        self.assertEqual(stable, "sdm://example-home/device-1")


if __name__ == "__main__":
    unittest.main()
