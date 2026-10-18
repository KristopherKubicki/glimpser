"""Dynamic desktop PNG sizes are not evidence of an unhealthy source."""

from unittest.mock import patch

import pytest

from app.utils import screenshots as ss


@pytest.mark.parametrize("path", ["DesktopOne", "DesktopTwo", "DesktopThree"])
def test_desktop_size_changes_are_accepted(path, monkeypatch):
    monkeypatch.setattr(
        ss.capture_policy,
        "CAPTURE_POLICY",
        {
            "variable_size_images": [
                {"host": "desktop.example.test", "path": f"/{path}.png"}
            ]
        },
    )
    url = f"http://desktop.example.test:9077/{path}.png"
    with (
        patch.object(ss, "content_length_cache", {url: 1000}),
        patch.object(ss, "content_length_cache_time", {}),
        patch.object(ss, "_persist_preflight_cache"),
        patch.object(ss, "record_preflight_backoff") as backoff,
    ):
        ss._set_content_length(url, 100000)
        backoff.assert_not_called()
        assert ss.content_length_cache[url] == 100000


@pytest.mark.parametrize(
    "url",
    [
        "http://desktop.example.test:9077/other.png",
        "http://example.com:9077/DesktopTwo.png",
        "http://desktop.example.test:80/DesktopTwo.png",
    ],
)
def test_other_sources_keep_size_guard(url):
    with (
        patch.object(ss, "content_length_cache", {url: 1000}),
        patch.object(ss, "content_length_cache_time", {}),
        patch.object(ss, "_persist_preflight_cache"),
        patch.object(ss, "record_preflight_backoff") as backoff,
    ):
        ss._set_content_length(url, 100000)
        assert backoff.call_args.args[1] == "content_length_variance"
