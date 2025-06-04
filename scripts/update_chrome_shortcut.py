import os
import sys
from pathlib import Path

try:
    import win32com.client  # type: ignore
except ImportError:  # pragma: no cover - platform specific
    win32com = None


FLAG = "--remote-debugging-port=9222"


def _update_shortcut(shortcut: Path, shell) -> bool:
    sc = shell.CreateShortcut(str(shortcut))
    args = sc.Arguments or ""
    if FLAG not in args:
        sc.Arguments = (args + " " + FLAG).strip()
        sc.Save()
        return True
    return False


def update_chrome_shortcuts() -> list[str]:
    """Update Chrome .lnk files to include the remote debugging flag.

    Returns a list of patched shortcut paths. An empty list indicates no
    shortcuts were modified or the platform does not support updates.
    """
    if os.name != "nt" or win32com is None:
        print("Shortcut update only supported on Windows with pywin32 installed")
        return []

    shell = win32com.client.Dispatch("WScript.Shell")
    locations = [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs",
        Path(os.environ.get("ProgramData", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs",
    ]

    updated: list[str] = []
    for loc in locations:
        if loc.exists():
            for shortcut in loc.rglob("*.lnk"):
                if "chrome" in shortcut.name.lower():
                    if _update_shortcut(shortcut, shell):
                        path = str(shortcut)
                        print(f"Updated {path}")
                        updated.append(path)
    return updated


if __name__ == "__main__":  # pragma: no cover - manual usage
    sys.exit(0 if update_chrome_shortcuts() else 1)
