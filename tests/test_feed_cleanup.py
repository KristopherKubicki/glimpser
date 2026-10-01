import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.utils import scheduling as sc
from app.utils import screenshots as ss
from app.utils import tv_guide as tv


def test_resource_skip_queues_one_camera_without_marking_offline():
    scheduler = MagicMock(running=True)
    scheduler.get_job.return_value = None
    with (
        patch.object(sc, "scheduler", scheduler),
        patch.object(sc, "get_template", return_value={"frequency": 30}),
        patch.object(sc, "is_system_online", return_value=True),
        patch.object(sc.psutil, "cpu_percent", return_value=99),
        patch.object(sc, "mark_offline") as offline,
        patch.object(sc.multiprocessing, "Process") as process,
    ):
        sc.run_with_timeout(sc.update_camera, ("camera", {}), 120)
        assert scheduler.add_job.call_args.kwargs["id"] == "resource_retry:camera"
        assert scheduler.add_job.call_args.kwargs["args"] == ["camera", {}, 120]
        scheduler.get_job.return_value = object()
        sc.run_with_timeout(sc.update_camera, ("camera", {}), 120)
        assert scheduler.add_job.call_count == 1
        offline.assert_not_called()
        process.assert_not_called()


def test_non_camera_and_archived_work_not_retried():
    scheduler = MagicMock(running=True)
    with (
        patch.object(sc, "scheduler", scheduler),
        patch.object(sc, "get_template", return_value={"groups": "archive"}),
    ):
        sc._defer_camera_for_resources(lambda: None, ("camera",), 120)
        sc._defer_camera_for_resources(sc.update_camera, ("camera",), 120)
        scheduler.add_job.assert_not_called()


def test_desktop_size_change_allowed_but_other_urls_still_guarded(monkeypatch):
    monkeypatch.setattr(
        ss.capture_policy,
        "CAPTURE_POLICY",
        {"variable_size_images": [{"host": "desktop.example", "path": "/Desktop.png"}]},
    )
    desktop = "http://desktop.example:9999/Desktop.png"
    other = "https://example.com/page"
    with (
        patch.object(ss, "content_length_cache", {desktop: 1000, other: 1000}),
        patch.object(ss, "content_length_cache_time", {}),
        patch.object(ss, "_persist_preflight_cache"),
        patch.object(ss, "record_preflight_backoff") as backoff,
    ):
        ss._set_content_length(desktop, 1000000)
        backoff.assert_not_called()
        ss._set_content_length(other, 1000000)
        assert backoff.call_args.args[1] == "content_length_variance"


def test_tv_fallback_labels_source_and_central_time():
    class Clock:
        @staticmethod
        def now(tz=None):
            return datetime(
                2026, 9, 25, 10, tzinfo=ZoneInfo("America/Chicago")
            ).astimezone(tz)

        fromisoformat = datetime.fromisoformat

    episodes = [
        {
            "airstamp": "2026-09-26T01:00:00+00:00",
            "name": "Episode",
            "show": {
                "name": "Tonight Show",
                "network": {"name": "ABC"},
                "summary": "<p>A show.</p>",
            },
        }
    ]

    def reader(url, timeout):
        return (
            '<div data-testid="featured-schedules-list"></div>'
            if "tvguide.com" in url
            else json.dumps(episodes)
        )

    with patch.object(tv, "datetime", Clock):
        result = tv.fetch_tv_guide_payload(reader)
    assert result["ok"]
    assert result["source_name"] == "TVmaze"
    assert result["cards"][0]["time"] == "08:00 PM CDT"
    assert result["cards"][0]["summary"] == "A show."


def test_tv_total_failure_is_explicit_and_not_exception():
    def reader(*args, **kwargs):
        raise TimeoutError()

    result = tv.fetch_tv_guide_payload(reader)
    assert result["ok"] is False
    assert result["cards"] == []
    assert "data unavailable" in result["message"]


def test_browser_queue_prioritizes_home_without_starving_public(tmp_path, monkeypatch):
    from app.utils import browser_queue as queue

    monkeypatch.setenv("GLIMPSER_BROWSER_QUEUE_PATH", str(tmp_path / "queue.sqlite"))
    queue.enqueue("public", {"groups": "news"})
    for index in range(4):
        queue.enqueue(f"Hubitat{index}", {})
    names = []
    for _ in range(4):
        turn = queue.claim()
        names.append(turn["name"])
        queue.finish(turn["name"], turn["token"], retry=False)
    assert names[:3] == ["Hubitat0", "Hubitat1", "Hubitat2"]
    assert names[3] == "public"
