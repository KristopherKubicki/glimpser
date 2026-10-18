import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def watchdog():
    path = Path(__file__).resolve().parents[1] / "scripts/kiosk_render_watchdog.py"
    spec = importlib.util.spec_from_file_location("watchdog_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree(title="Glimpser - Dashboard", identity="glimpser.home.arpa", size="1920x1080"):
    return f'  0xe00003 "{title}": ("{identity}" "Google-chrome") {size}+0+0 +0+0'


@pytest.mark.parametrize(
    "title",
    [
        "Glimpser - Dashboard",
        "glimpser.home.arpa",
        "This site can’t be reached",
        "Privacy error",
        "",
    ],
)
def test_title_changes_do_not_hide_the_kiosk(watchdog, title):
    assert watchdog.kiosk_window_id(tree(title)) == 0xE00003


@pytest.mark.parametrize(
    "identity,size",
    [
        ("google-chrome", "1920x1080"),
        ("example.com", "1920x1080"),
        ("glimpser.home.arpa", "800x600"),
    ],
)
def test_other_windows_are_not_selected(watchdog, identity, size):
    assert watchdog.kiosk_window_id(tree(identity=identity, size=size)) is None


@pytest.mark.parametrize("focused,expected", [(0xE00003, True), (0x123, False)])
def test_keyboard_recovery_requires_kiosk_focus(
    watchdog, monkeypatch, focused, expected
):
    monkeypatch.setattr(
        watchdog.subprocess,
        "check_output",
        lambda *a, **k: tree("This site can’t be reached"),
    )
    x, xt = MagicMock(), MagicMock()
    x.XOpenDisplay.return_value = 1
    x.XGetInputFocus.side_effect = lambda display, focus, revert: setattr(
        focus._obj, "value", focused
    )
    x.XKeysymToKeycode.return_value = 10
    monkeypatch.setattr(
        watchdog.ctypes, "CDLL", lambda library: xt if "Xtst" in library else x
    )
    assert watchdog.close_kiosk() is expected
    assert xt.XTestFakeKeyEvent.call_count == (4 if expected else 0)
    x.XCloseDisplay.assert_called_once_with(1)


@pytest.mark.parametrize(
    "age,healthy,cooldown,expected",
    [
        (None, 299, 600, False),
        (None, 300, 600, True),
        (300, 179, 600, False),
        (300, 180, 599, False),
        (300, 180, 600, True),
        (15, 600, 600, False),
    ],
)
def test_existing_outage_cooldown_and_freshness_gates(
    watchdog, age, healthy, cooldown, expected
):
    assert watchdog.should_recover(age, healthy, cooldown) is expected
