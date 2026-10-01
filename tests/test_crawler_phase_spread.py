"""Regression checks for recurring startup phases and priority deadline bursts."""

from collections import Counter
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.utils import scheduling


def test_mixed_intervals_do_not_collapse_at_end_of_startup():
    templates = {
        f"camera-{index}": {"frequency": frequency}
        for index, frequency in enumerate(
            ([1] * 20 + [5] * 80 + [15] * 100 + [60] * 100)
        )
    }
    offsets = scheduling.calculate_optimal_offsets(templates, 10)
    assert offsets == scheduling.calculate_optimal_offsets(
        dict(reversed(list(templates.items()))), 10
    )
    starts = Counter()
    for name, offset in offsets.items():
        interval = templates[name]["frequency"] * 60
        assert 0 <= offset < min(600, interval)
        for tick in range(offset, 3600, interval):
            starts[tick // 10] += 1
    # Formerly hundreds of starts bunched into the last ten startup seconds.
    assert max(starts.values()) <= 20


@pytest.mark.parametrize("frequency", [None, "invalid", 0, -1])
def test_invalid_or_nonpositive_frequency_does_not_break_all_scheduling(frequency):
    offsets = scheduling.calculate_optimal_offsets(
        {"camera": {"frequency": frequency}}, 10
    )
    assert 0 <= offsets["camera"] < 600


def test_empty_and_disabled_spread():
    assert scheduling.calculate_optimal_offsets({}, 10) == {}
    assert scheduling.calculate_optimal_offsets({"camera": {"frequency": 5}}, 0) == {
        "camera": 0
    }


def test_priority_jitter_wraps_instead_of_clamping_to_one_deadline(
    monkeypatch, tmp_path
):
    templates = {
        name: {"name": name, "frequency": 1, "groups": "priority"}
        for name in ("one", "two")
    }
    scheduler = Mock()
    scheduler.get_jobs.return_value = []
    monkeypatch.setattr(scheduling, "scheduler", scheduler)
    monkeypatch.setattr(scheduling, "get_templates", lambda: templates)
    monkeypatch.setattr(
        scheduling, "calculate_optimal_offsets", lambda *args: {"one": 50, "two": 55}
    )
    monkeypatch.setattr(scheduling, "LOW_CPU_MODE", False)
    monkeypatch.setattr(scheduling, "CRAWLER_SCHEDULE_JITTER_SECONDS", 15)
    monkeypatch.setattr(scheduling.random, "randint", lambda *args: 15)
    monkeypatch.setattr(scheduling, "SCREENSHOT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(scheduling, "VIDEO_DIRECTORY", str(tmp_path))
    before = datetime.now()
    scheduling.schedule_crawlers()
    jobs = {call.kwargs["id"]: call.kwargs for call in scheduler.add_job.call_args_list}
    assert 5 <= (jobs["one"]["start_date"] - before).total_seconds() < 6
    assert 10 <= (jobs["two"]["start_date"] - before).total_seconds() < 11
    assert jobs["one"]["seconds"] == jobs["two"]["seconds"] == 60
