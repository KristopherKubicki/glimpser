import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import update_chrome_shortcut  # noqa: E402


class TestShortcutsNeedPatch(unittest.TestCase):
    def _setup_env(self, tmpdir: str):
        env = {"USERPROFILE": tmpdir, "APPDATA": tmpdir, "ProgramData": tmpdir}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        desktop = Path(tmpdir) / "Desktop"
        desktop.mkdir()
        return desktop

    def _win32_stub(self, arg: str):
        class Shell:
            def CreateShortcut(self, _):
                return SimpleNamespace(Arguments=arg)

        return SimpleNamespace(client=SimpleNamespace(Dispatch=lambda *_: Shell()))

    def _patch_os(self):
        fake_os = SimpleNamespace(name="nt", environ=os.environ)
        return patch.object(update_chrome_shortcut, "os", fake_os)

    def test_needs_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            desktop = self._setup_env(tmpdir)
            (desktop / "Chrome.lnk").touch()
            stub = self._win32_stub("")
            with (
                self._patch_os(),
                patch.object(update_chrome_shortcut, "win32com", stub),
            ):
                self.assertTrue(update_chrome_shortcut.shortcuts_need_patch())

    def test_no_patch_needed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            desktop = self._setup_env(tmpdir)
            (desktop / "Chrome.lnk").touch()
            stub = self._win32_stub(update_chrome_shortcut.FLAG)
            with (
                self._patch_os(),
                patch.object(update_chrome_shortcut, "win32com", stub),
            ):
                self.assertFalse(update_chrome_shortcut.shortcuts_need_patch())


if __name__ == "__main__":
    unittest.main()
