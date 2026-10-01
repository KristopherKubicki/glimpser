"""One unavailable Google camera must not block other local preview pages."""

import pytest

from app.utils import screenshots as ss


def preview(device, token="first"):
    return f"http://127.0.0.1:80/integrations/google/webrtc/preview?profile=example-office&device_id={device}&token={token}"


@pytest.fixture(autouse=True)
def isolated_caches(monkeypatch):
    for name in (
        "tier_cache",
        "domain_backoff_cache",
        "domain_retry_budget_cache",
        "source_circuit_cache",
        "_tier_failure_log_cache",
    ):
        monkeypatch.setattr(ss, name, {})
    monkeypatch.setattr(ss, "_persist_preflight_cache", lambda: None)


def test_unavailable_camera_does_not_block_healthy_peer():
    bad = preview("Unavailable")
    good = preview("Healthy")
    ss._record_tier_failure(bad, ss.TIER_HEADLESS, "browser_timeout")
    assert not ss._tier_allowed(bad, ss.TIER_HEADLESS)
    assert not ss._tier_allowed("sdm://example-office/Unavailable", ss.TIER_HEADLESS)
    assert ss._tier_allowed(good, ss.TIER_HEADLESS)
    assert ss._tier_allowed("sdm://example-office/Healthy", ss.TIER_HEADLESS)


def test_preview_tokens_share_only_their_camera_budget(monkeypatch):
    monkeypatch.setattr(ss, "DOMAIN_RETRY_BUDGET_LIMIT", 1)
    assert ss._consume_domain_retry_budget(preview("A"))[0]
    assert not ss._consume_domain_retry_budget(preview("A", "renewed"))[0]
    assert ss._consume_domain_retry_budget(preview("B"))[0]
    assert ss._source_circuit_key(preview("A")) == "sdm://example-office/A"


def test_domain_backoff_is_local_to_camera():
    ss._set_domain_backoff(preview("A"), "unavailable", 60)
    assert ss._domain_backoff_active("sdm://example-office/A")[0]
    assert not ss._domain_backoff_active(preview("B"))[0]


def test_expired_lock_restores_browser_capture(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ss.time, "time", lambda: now[0])
    url = preview("A")
    ss._record_tier_failure(url, ss.TIER_HEADLESS, "browser_timeout")
    assert not ss._tier_allowed(url, ss.TIER_HEADLESS)
    now[0] = ss.tier_cache[ss._tier_key(url)]["lock_until"] + 1
    assert ss._tier_allowed(url, ss.TIER_HEADLESS)
    assert "max_tier" not in ss.tier_cache[ss._tier_key(url)]


def test_legacy_loopback_lock_does_not_disable_all_google_feeds():
    ss.tier_cache["127.0.0.1:80"] = {"lock_until": float("inf"), "max_tier": 0}
    assert ss._tier_allowed(preview("A"), ss.TIER_HEADLESS)
    assert not ss._tier_allowed("http://127.0.0.1:80/other", ss.TIER_HEADLESS)


def test_ordinary_domains_keep_existing_host_scope():
    assert ss._tier_key("https://example.com/a") == ss._tier_key(
        "https://example.com/b"
    )
    assert ss._domain_key("https://example.com/a") == "example.com"
