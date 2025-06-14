import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import update_chrome_shortcut


class TestShortcutExecLine(unittest.TestCase):
    def test_linux_exec_line(self):
        tmp = Path("/tmp/test.desktop")
        tmp.write_text("Exec=/usr/bin/chrome --flag\n", encoding="utf-8")
        line = update_chrome_shortcut.shortcut_exec_line(tmp)
        self.assertEqual(line, "/usr/bin/chrome --flag")
        tmp.unlink()

    def test_windows_exec_line(self):
        stub = SimpleNamespace(
            client=SimpleNamespace(
                Dispatch=lambda *_: SimpleNamespace(
                    CreateShortcut=lambda *_: SimpleNamespace(
                        TargetPath="chrome.exe", Arguments="--port"
                    )
                )
            )
        )
        path = Path("Chrome.lnk")
        path.touch()
        with (
            patch.object(update_chrome_shortcut, "os", SimpleNamespace(name="nt")),
            patch.object(update_chrome_shortcut, "win32com", stub),
        ):
            line = update_chrome_shortcut.shortcut_exec_line(path)
        self.assertEqual(line, "chrome.exe --port")
        path.unlink()


if __name__ == "__main__":
    unittest.main()
