from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

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


def test_save_snapshot_png_uses_shared_still_postprocess(monkeypatch, tmp_path) -> None:
    source = Image.new("RGB", (40, 30), (20, 20, 20))
    buffer = BytesIO()
    source.save(buffer, format="PNG")

    seen: dict[str, object] = {}

    def _postprocess(image, final_path, name, **kwargs):
        seen["name"] = name
        seen["final_path"] = final_path
        seen["kwargs"] = kwargs
        return image.crop((0, 0, 20, 10))

    monkeypatch.setattr(eufy_first_pass, "SCREENSHOT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(
        eufy_first_pass.screenshots,
        "_postprocess_still_image",
        _postprocess,
    )
    monkeypatch.setattr(
        eufy_first_pass.screenshots, "add_timestamp", lambda *a, **k: None
    )

    out = eufy_first_pass._save_snapshot_png(
        name="BeachShore",
        payload=buffer.getvalue(),
        invert=False,
        dark=False,
        stabilize_mode="rolling_5m",
    )

    assert seen["name"] == "BeachShore"
    assert seen["kwargs"]["stabilize_mode"] == "rolling_5m"
    assert Image.open(out).size == (20, 10)


def test_save_snapshot_png_rejects_processed_loading_frame(
    monkeypatch, tmp_path
) -> None:
    source = Image.new("RGB", (40, 30), (20, 20, 20))
    buffer = BytesIO()
    source.save(buffer, format="PNG")

    monkeypatch.setattr(eufy_first_pass, "SCREENSHOT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(
        eufy_first_pass.screenshots,
        "_postprocess_still_image",
        lambda image, *_args, **_kwargs: image,
    )
    monkeypatch.setattr(
        eufy_first_pass.screenshots,
        "_captured_frame_rejection_reason",
        lambda image: "loading",
    )

    with pytest.raises(eufy_cloud.EufyCloudError, match="loading"):
        eufy_first_pass._save_snapshot_png(
            name="BeachShore",
            payload=buffer.getvalue(),
            invert=False,
        )
