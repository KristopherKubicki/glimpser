from unittest.mock import Mock

import pytest

from app import routes


@pytest.mark.parametrize(
    "seconds,attempts,expected_probes,expected_sleep",
    [(None, 2, 2, 2), (3, 99, 2, 3), (None, None, 3, 6)],
)
def test_failed_http_probes_stop_at_budget(
    monkeypatch, seconds, attempts, expected_probes, expected_sleep
):
    clock = [100.0]
    sleeps = []

    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
        assert len(sleeps) <= 4, "unbounded connectivity retry"

    probe = Mock(return_value=False)
    failure = Mock()
    launch = Mock(
        side_effect=AssertionError("unreachable source must not launch encoder")
    )
    monkeypatch.setattr(routes.time, "time", lambda: clock[0])
    monkeypatch.setattr(routes.time, "sleep", sleep)
    monkeypatch.setattr(routes, "check_url_accessible", probe)
    monkeypatch.setattr(routes, "build_live_ffmpeg_command", lambda *a, **k: [])
    monkeypatch.setattr(routes.config, "LIVE_MAX_FAILURES", 3)
    monkeypatch.setattr(routes, "live_host_key", lambda _: None)
    monkeypatch.setattr(routes.live_caps, "record_failure", failure)
    monkeypatch.setattr(routes.subprocess, "Popen", launch)
    assert (
        list(
            routes.generate_live_stream(
                "https://example.test/live.m3u8",
                max_no_output_seconds=seconds,
                max_no_output_failures=attempts,
            )
        )
        == []
    )
    assert probe.call_count == expected_probes
    assert sum(sleeps) == expected_sleep
    launch.assert_not_called()
    failure.assert_called_once()


def test_http_probe_uses_one_request_path_with_default_tls_verification(monkeypatch):
    probe = Mock(return_value=(True, {"ok": True}))
    monkeypatch.setattr(routes, "probe_url_with_range", probe)
    assert routes.check_url_accessible("https://example.test/live.m3u8")
    assert probe.call_args.kwargs["preconnect"] is False
    assert "verify" not in probe.call_args.kwargs


def test_successful_probe_cannot_launch_encoder_after_deadline(monkeypatch):
    clock = [100.0]

    def probe(url):
        clock[0] += 4
        return True

    launch = Mock()
    monkeypatch.setattr(routes.time, "time", lambda: clock[0])
    monkeypatch.setattr(routes, "check_url_accessible", probe)
    monkeypatch.setattr(routes, "build_live_ffmpeg_command", lambda *a, **k: [])
    monkeypatch.setattr(routes, "live_host_key", lambda _: None)
    monkeypatch.setattr(routes.live_caps, "record_failure", Mock())
    monkeypatch.setattr(routes.subprocess, "Popen", launch)
    assert (
        list(
            routes.generate_live_stream(
                "https://example.test/live.m3u8", max_no_output_seconds=3
            )
        )
        == []
    )
    launch.assert_not_called()
