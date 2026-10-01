"""Operator-declared outages stay visible without counting as live failures."""

import sqlite3

from app.runtime_health import capture_health
from app.utils.camera_health import build_camera_health_report


def test_expected_offline_keeps_failure_evidence_but_not_actionable_count(tmp_path):
    report = build_camera_health_report(
        {
            "Bodycam": {
                "groups": "mobile,expected-offline",
                "capture_failed": True,
                "offline_since": "2026-09-28 00:00:00",
                "notes": "Operator status: disconnected on desk.\nOther notes.",
            },
            "Broken": {"capture_failed": True},
        },
        tmp_path / "screenshots",
        tmp_path / "videos",
    )
    bodycam = next(row for row in report["cameras"] if row["name"] == "Bodycam")
    assert bodycam["status"] == "expected_offline"
    assert bodycam["capture_failed"] is True
    assert "capture_failed=1" in bodycam["issues"]
    assert bodycam["operator_note"] == "Operator status: disconnected on desk."
    assert report["summary"]["expected_offline"] == 1
    assert report["summary"]["capture_failing"] == 1
    assert report["summary"]["failing"] == 1


def test_removing_tag_restores_actionable_failure(tmp_path):
    report = build_camera_health_report(
        {"Bodycam": {"groups": "mobile", "capture_failed": True}}, tmp_path, tmp_path
    )
    assert report["cameras"][0]["status"] == "failing"
    assert report["cameras"][0]["expected_offline"] is False


def test_database_summary_separates_expected_offline(tmp_path):
    path = tmp_path / "health.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE templates (frequency, last_screenshot_time, capture_failed, groups)"
        )
        db.executemany(
            "INSERT INTO templates VALUES (30, '', 1, ?)",
            [("expected-offline",), ("camera",), ("archive,expected-offline",)],
        )
    summary = capture_health(str(path))
    assert summary["total"] == 3
    assert summary["active"] == 1
    assert summary["archived"] == 1
    assert summary["expected_offline"] == 1
    assert summary["failed"] == 1


def test_private_archive_alias_is_shared_by_health_and_backfill(tmp_path, monkeypatch):
    import json
    import os
    import subprocess
    import sys

    settings = tmp_path / "viewer.json"
    settings.write_text(json.dumps({"archived_groups": ["Example-Stale"]}))
    path = tmp_path / "private-health.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE templates (frequency, last_screenshot_time, capture_failed, groups)"
        )
        db.execute("INSERT INTO templates VALUES (30, '', 1, 'example-stale')")
    script = """
import sys
from app import runtime_health, viewer_policy
from app.utils import camera_health
from scripts import backfill_stale_captions as backfill
expected = {'archive', 'source-stale', 'example-stale'}
assert viewer_policy.ARCHIVE_GROUPS == expected
assert runtime_health.ARCHIVE_GROUPS is viewer_policy.ARCHIVE_GROUPS
assert camera_health.ARCHIVE_GROUPS is viewer_policy.ARCHIVE_GROUPS
assert expected <= backfill.DEFAULT_SKIP_GROUPS
assert runtime_health.capture_health(sys.argv[1])['archived'] == 1
report = camera_health.build_camera_health_report(
    {'ExampleCamera': {'groups': 'example-stale', 'capture_failed': True}},
    sys.argv[2], sys.argv[2],
)
assert report['cameras'][0]['status'] == 'archived'
"""
    env = {**os.environ, "GLIMPSER_VIEWER_CONFIG": str(settings)}
    result = subprocess.run(
        [sys.executable, "-c", script, str(path), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
