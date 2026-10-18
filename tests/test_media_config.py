"""Personal workers have no implicit remote inference target or account fallback."""

import json

import pytest

from scripts.media_config import load_media_config, review_command


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "media.json"
    monkeypatch.setenv("GLIMPSER_MEDIA_CONFIG", str(path))
    return path


def test_missing_target_never_builds_ssh_command(settings):
    assert load_media_config() == {}
    with pytest.raises(RuntimeError, match="not configured"):
        review_command("feed_tv")


def test_fixed_personal_worker(settings):
    settings.write_text(
        json.dumps(
            {
                "scope": "personal",
                "personal_review_host": "owner@personal.example",
                "ssh_identity": "/keys/personal",
            }
        )
    )
    command = review_command("magazine")
    assert command[-3:] == [
        "owner@personal.example",
        "python3",
        ".local/lib/glimpser-magazine/review.py",
    ]
    assert "StrictHostKeyChecking=yes" in command
    with pytest.raises(ValueError, match="Unknown"):
        review_command("arbitrary command")


@pytest.mark.parametrize(
    "data",
    [
        {"scope": "work"},
        {"scope": "personal", "personal_review_host": "-oProxyCommand=command"},
        {"scope": "personal", "personal_review_host": "host; command"},
        {"scope": "personal", "collect_cameras": ["../outside"]},
        {"scope": "personal", "data_root": "relative"},
    ],
)
def test_invalid_configuration_stops_worker(settings, data):
    settings.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_media_config()
