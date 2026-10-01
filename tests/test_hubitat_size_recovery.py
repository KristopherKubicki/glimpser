from unittest.mock import patch

from app.utils import screenshots as ss


def test_hubitat_cloud_recovery_not_blocked_by_error_page_size():
    dashboard = "https://cloud.hubitat.com/api/hub/apps/17/ui?access_token=test"
    ordinary = "https://example.com/apps/17/ui"
    urls = [dashboard, ordinary]
    with (
        patch.object(ss, "content_length_cache", dict.fromkeys(urls, 100)),
        patch.object(ss, "content_length_cache_time", {}),
        patch.object(ss, "_persist_preflight_cache"),
        patch.object(ss, "record_preflight_backoff") as backoff,
    ):
        ss._set_content_length(dashboard, 100000)
        backoff.assert_not_called()
        assert ss.content_length_cache[dashboard] == 100000
        ss._set_content_length(ordinary, 100000)
        assert backoff.call_args.args[:2] == (ordinary, "content_length_variance")
