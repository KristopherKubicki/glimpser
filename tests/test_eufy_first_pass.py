from __future__ import annotations

import pytest

from app.utils import eufy_cloud, eufy_first_pass


def test_capture_profile_first_pass_success(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "get_templates",
        lambda: {
            "Backyard": {"url": "eufy://default/dev-1", "invert": False},
            "Other": {"url": "http://example.test"},
        },
    )
    monkeypatch.setattr(
        eufy_first_pass.eufy_cloud,
        "fetch_snapshot",
        lambda profile, device_id, timeout: (b"jpeg-bytes", "image/jpeg"),
    )
    monkeypatch.setattr(
        eufy_first_pass,
        "_save_snapshot_png",
        lambda **kwargs: "/tmp/backyard.png",
    )

    seen: dict[str, list[object]] = {"updated": [], "cleared": [], "failed": []}
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "update_last_screenshot_time",
        lambda name: seen["updated"].append(name),
    )
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "clear_offline",
        lambda name: seen["cleared"].append(name),
    )
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "set_capture_failed",
        lambda name, failed: seen["failed"].append((name, bool(failed))),
    )

    rows = eufy_first_pass.capture_profile_first_pass("default", timeout=9.0)
    assert len(rows) == 1
    assert rows[0]["name"] == "Backyard"
    assert rows[0]["ok"] is True
    assert rows[0]["file"] == "/tmp/backyard.png"
    assert seen["updated"] == ["Backyard"]
    assert seen["cleared"] == ["Backyard"]
    assert seen["failed"] == [("Backyard", False)]


def test_capture_profile_first_pass_marks_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "get_templates",
        lambda: {"Backyard": {"url": "eufy://default/dev-1", "invert": False}},
    )

    def _fail_fetch(profile, device_id, timeout):
        raise RuntimeError("snapshot error")

    monkeypatch.setattr(eufy_first_pass.eufy_cloud, "fetch_snapshot", _fail_fetch)
    monkeypatch.setattr(
        eufy_first_pass,
        "_save_snapshot_png",
        lambda **kwargs: "/tmp/ignored.png",
    )

    seen: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "update_last_screenshot_time",
        lambda name: None,
    )
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "clear_offline",
        lambda name: None,
    )
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "set_capture_failed",
        lambda name, failed: seen.append((name, bool(failed))),
    )

    rows = eufy_first_pass.capture_profile_first_pass("default", timeout=9.0)
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert "snapshot error" in rows[0]["error"]
    assert seen == [("Backyard", True)]


def test_capture_profile_first_pass_bubbles_captcha(monkeypatch) -> None:
    monkeypatch.setattr(
        eufy_first_pass.template_manager,
        "get_templates",
        lambda: {"Backyard": {"url": "eufy://default/dev-1", "invert": False}},
    )

    def _captcha_fetch(profile, device_id, timeout):
        raise eufy_cloud.EufyCaptchaRequired(
            "default",
            "cid-1",
            "data:image/png;base64,abc",
            "captcha required",
        )

    monkeypatch.setattr(
        eufy_first_pass.eufy_cloud,
        "fetch_snapshot",
        _captcha_fetch,
    )

    with pytest.raises(eufy_cloud.EufyCaptchaRequired):
        eufy_first_pass.capture_profile_first_pass("default", timeout=9.0)
