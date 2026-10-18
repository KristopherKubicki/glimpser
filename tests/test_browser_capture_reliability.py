"""Regression coverage for rejected browser pages and source-local failures."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from selenium.common.exceptions import TimeoutException, WebDriverException

from app.utils import screenshots as ss


@pytest.fixture
def browser(monkeypatch, tmp_path):
    driver = MagicMock()
    driver.execute_script.return_value = ""
    monkeypatch.setattr(ss, "throttle_cache", {})
    monkeypatch.setattr(ss, "_persist_preflight_cache", lambda: None)
    monkeypatch.setattr(ss, "is_system_online", lambda: True)
    monkeypatch.setattr(ss, "get_chrome_path", lambda: sys.executable)
    monkeypatch.setattr(ss, "get_chrome_version", lambda _: 120)
    monkeypatch.setattr(ss, "launch_headless_chrome", lambda *a, **k: driver)
    monkeypatch.setattr(ss, "_browser_capture_profile", lambda *a: {})
    monkeypatch.setattr(ss, "_browser_profile_chrome_args", lambda *a: [])
    monkeypatch.setattr(
        ss, "_acquire_browser_capture_file_lock", lambda *a, **k: (True, None)
    )
    monkeypatch.setattr(ss, "cleanup_old_tempdirs", lambda *a, **k: None)
    monkeypatch.setattr(ss, "cleanup_orphaned_browser_processes", lambda: None)
    monkeypatch.setattr(ss, "kill_driver_process", lambda _: None)
    monkeypatch.setattr(ss.time, "sleep", lambda _: None)
    return driver


@pytest.mark.parametrize("late", [False, True])
def test_browser_error_preserves_previous_image(browser, monkeypatch, tmp_path, late):
    output = tmp_path / "camera.png"
    output.write_bytes(b"previous accepted image")
    calls = 0

    def script(source, *args):
        nonlocal calls
        if "location.protocol" in source:
            calls += 1
            return "browser_error_page" if not late or calls > 1 else ""
        return 0

    browser.execute_script.side_effect = script
    browser.save_screenshot.side_effect = lambda path: Path(path).write_bytes(
        b"bad page"
    )
    finalize = MagicMock()
    monkeypatch.setattr(ss, "_finalize_screenshot", finalize)
    url = "https://camera.example/"
    assert ss.capture_screenshot_and_har(url, str(output), stealth=False) is False
    assert output.read_bytes() == b"previous accepted image"
    assert not (tmp_path / "camera.png.tmp.png").exists()
    finalize.assert_not_called()
    assert ss.throttle_cache[url]["reason"] == "browser_error_page"
    assert ss._renderer_healthy("headless")
    browser.quit.assert_called_once()


def test_unready_sdm_never_falls_back_to_status_page(browser, monkeypatch, tmp_path):
    finalize = MagicMock()
    monkeypatch.setattr(ss, "_finalize_screenshot", finalize)
    url = "http://127.0.0.1/integrations/google/webrtc/preview"
    assert (
        ss.capture_screenshot_and_har(url, str(tmp_path / "cam.png"), stealth=False)
        is False
    )
    browser.save_screenshot.assert_not_called()
    finalize.assert_not_called()
    assert ss.throttle_cache[url]["reason"] == "sdm_preview_not_ready"


def test_ready_sdm_captures_camera_region(browser, monkeypatch, tmp_path):
    element = MagicMock()
    element.rect = {"width": 1280, "height": 720}
    element.screenshot.side_effect = lambda path: Image.effect_noise(
        (1280, 720), 80
    ).save(path)
    browser.find_element.return_value = element

    def script(source, *args):
        if "sdmState" in source:
            return {"ready": "1", "state": "ready"}
        if "tagName.toLowerCase" in source:
            return "div"
        if "clientWidth" in source:
            return 1280
        if "clientHeight" in source:
            return 720
        return ""

    browser.execute_script.side_effect = script
    finalize = MagicMock(return_value=True)
    monkeypatch.setattr(ss, "_finalize_screenshot", finalize)
    url = "http://127.0.0.1/integrations/google/webrtc/preview"
    assert (
        ss.capture_screenshot_and_har(
            url,
            str(tmp_path / "cam.png"),
            dedicated_selector="//*[@id='stage']",
            stealth=False,
        )
        is True
    )
    element.screenshot.assert_called_once()
    browser.save_screenshot.assert_not_called()
    finalize.assert_called_once()


def test_startup_failure_retains_global_circuit_breaker(browser, monkeypatch, tmp_path):
    monkeypatch.setattr(
        ss,
        "launch_headless_chrome",
        MagicMock(side_effect=WebDriverException("cannot start")),
    )
    assert (
        ss.capture_screenshot_and_har(
            "https://camera.example/", str(tmp_path / "cam.png"), stealth=False
        )
        is False
    )
    assert not ss._renderer_healthy("headless")
    assert ss.throttle_cache["renderer:headless"]["reason"] == "startup_failed"


def test_navigation_timeout_does_not_disable_browser(browser, tmp_path):
    browser.get.side_effect = TimeoutException()
    assert (
        ss.capture_screenshot_and_har(
            "https://slow.example/", str(tmp_path / "cam.png"), stealth=False
        )
        is False
    )
    assert ss._renderer_healthy("headless")


@pytest.mark.parametrize("elapsed", [1, 50])
def test_failed_source_does_not_block_next_source(monkeypatch, tmp_path, elapsed):
    monkeypatch.setattr(ss, "throttle_cache", {})
    monkeypatch.setattr(ss, "SCREENSHOT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(ss, "_persist_preflight_cache", lambda: None)
    monkeypatch.setattr(ss, "_preflight_dns_tls", lambda *a, **k: (True, ""))
    monkeypatch.setattr(ss, "is_address_reachable", lambda *a, **k: True)
    monkeypatch.setattr(
        ss, "get_content_type", lambda *a, **k: ("text/html", False, True, "")
    )
    monkeypatch.setattr(ss, "_tier_allowed", lambda *a: True)
    monkeypatch.setattr(ss, "_method_allowed", lambda *a: True)
    now = [1000.0]
    monkeypatch.setattr(ss.time, "time", lambda: now[0])
    captured = []

    def capture(**kwargs):
        captured.append(kwargs["url"])
        now[0] += elapsed
        return len(captured) > 1

    monkeypatch.setattr(ss, "capture_screenshot_and_har", capture)
    template = {"browser": True, "headless": True, "timeout": 30}
    failed = "https://slow.example/"
    healthy = "https://healthy.example/"
    assert (
        ss._capture_or_download_inner("bad", template, failed, failed, None, None)
        is False
    )
    assert ss._renderer_healthy("headless")
    assert (
        ss._capture_or_download_inner("good", template, healthy, healthy, None, None)
        is True
    )
    assert captured == [failed, healthy]


@pytest.mark.parametrize("profile_delay", [0, 6])
def test_browser_error_releases_worker_before_settle_wait(
    browser, monkeypatch, tmp_path, profile_delay
):
    monkeypatch.setattr(
        ss, "_browser_capture_profile", lambda *a: {"post_load_delay": profile_delay}
    )
    sleep = MagicMock()
    monkeypatch.setattr(ss.time, "sleep", sleep)
    browser.execute_script.side_effect = lambda script, *args: (
        "browser_error_page" if "location.protocol" in script else ""
    )
    output = tmp_path / "camera.png"
    output.write_bytes(b"previous accepted image")
    assert not ss.capture_screenshot_and_har(
        "https://camera.example/", str(output), stealth=False
    )
    sleep.assert_not_called()
    browser.save_screenshot.assert_not_called()
    browser.quit.assert_called_once()
    assert output.read_bytes() == b"previous accepted image"


def test_normal_page_keeps_settle_wait_and_late_error_check(
    browser, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        ss, "_browser_capture_profile", lambda *a: {"post_load_delay": 6}
    )
    sleeps = []
    monkeypatch.setattr(ss.time, "sleep", sleeps.append)
    browser.execute_script.side_effect = lambda script, *args: (
        "browser_error_page" if "location.protocol" in script and sleeps else ""
    )
    assert not ss.capture_screenshot_and_har(
        "https://camera.example/", str(tmp_path / "camera.png"), stealth=False
    )
    assert sleeps == [5, 6]
    browser.quit.assert_called_once()
    browser.save_screenshot.assert_not_called()
