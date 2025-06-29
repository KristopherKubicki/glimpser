import os
import sys
from pathlib import Path

try:
    import win32com.client  # type: ignore
except ImportError:  # pragma: no cover - platform specific
    win32com = None

from app import config

FLAG = f"--remote-debugging-port={config.DANGER_PORT}"


LINUX_PATHS = [
    Path.home() / ".local/share/applications/google-chrome.desktop",
    Path.home() / ".local/share/applications/chromium.desktop",
    Path("/usr/share/applications/google-chrome.desktop"),
    Path("/usr/share/applications/chromium-browser.desktop"),
    Path("/usr/share/applications/chromium.desktop"),
]

MAC_DIRS = [Path("/Applications"), Path.home() / "Applications"]


def _update_shortcut(shortcut: Path, shell) -> bool:
    sc = shell.CreateShortcut(str(shortcut))
    args = sc.Arguments or ""
    if FLAG not in args:
        sc.Arguments = (args + " " + FLAG).strip()
        sc.Save()
        return True
    return False


def _update_desktop_file(desktop: Path) -> bool:
    """Add the debug flag to a .desktop file if missing."""
    if not desktop.exists() or not os.access(desktop, os.W_OK):
        return False
    lines = desktop.read_text(encoding="utf-8").splitlines()
    updated = False
    for idx, line in enumerate(lines):
        if line.startswith("Exec="):
            if FLAG not in line:
                lines[idx] = line.rstrip() + " " + FLAG
                updated = True
            break
    if updated:
        desktop.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return updated


def _update_macos_script(script: Path) -> bool:
    """Add the debug flag to a macOS script-based shortcut."""
    if not script.exists() or not os.access(script, os.W_OK):
        return False
    try:
        text = script.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    if FLAG in text:
        return False
    script.write_text(text.rstrip() + f" {FLAG}\n", encoding="utf-8")
    return True


def _mac_shortcut_paths() -> list[Path]:
    paths: list[Path] = []
    for base in MAC_DIRS:
        if base.exists():
            for item in base.iterdir():
                if item.suffix.lower() in {".command", ".applescript", ".sh"}:
                    paths.append(item)
                elif item.suffix == ".app":
                    target = item / "Contents" / "MacOS" / item.stem
                    if target.exists():
                        paths.append(target)
    return paths


def update_chrome_shortcuts() -> list[Path]:
    """Update Chrome shortcuts and return paths that were modified."""
    if os.name == "nt" and win32com is not None:
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

        updated: list[Path] = []
        for loc in locations:
            if loc.exists():
                for shortcut in loc.rglob("*.lnk"):
                    if "chrome" in shortcut.name.lower():
                        if _update_shortcut(shortcut, shell):
                            updated.append(shortcut)
        return updated

    if sys.platform == "darwin":
        updated: list[Path] = []
        for script in _mac_shortcut_paths():
            if "chrome" in script.name.lower():
                if _update_macos_script(script):
                    updated.append(script)
        return updated

    updated = []
    for path in LINUX_PATHS:
        if _update_desktop_file(path):
            updated.append(path)
    return updated


def update_chrome_shortcuts_info(path: Path | None = None) -> tuple[list[Path], str]:
    """Return updated paths and a message describing the result."""
    if path is not None:
        if sys.platform == "darwin":
            paths = [path] if _update_macos_script(path) else []
        else:
            paths = [path] if _update_desktop_file(path) else []
    else:
        paths = update_chrome_shortcuts()

    if paths:
        return paths, ""

    if not shortcuts_need_patch(path):
        return [], "Chrome shortcuts already include the debugging flag"

    if os.name == "nt" and win32com is None:
        return [], "Shortcut update only supported on Windows with pywin32 installed"

    return [], "No Chrome shortcuts were updated. Check your permissions"


def shortcuts_need_patch(path: Path | None = None) -> bool:
    """Return True if any Chrome shortcuts are missing the debug flag."""
    if os.name == "nt" and win32com is not None:
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

        for loc in locations:
            if loc.exists():
                for shortcut in loc.rglob("*.lnk"):
                    if "chrome" in shortcut.name.lower():
                        sc = shell.CreateShortcut(str(shortcut))
                        args = sc.Arguments or ""
                        if FLAG not in args:
                            return True
        return False

    if sys.platform == "darwin":
        paths = [path] if path else _mac_shortcut_paths()
        for script in paths:
            if script.exists():
                try:
                    text = script.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if FLAG not in text:
                    return True
        return False

    paths = [path] if path else LINUX_PATHS
    for desktop in paths:
        if desktop.exists():
            text = desktop.read_text(encoding="utf-8")
            if "Exec=" in text and FLAG not in text:
                return True
    return False


def first_shortcut_path() -> Path | None:
    """Return the first Chrome shortcut found in standard locations."""
    if os.name == "nt" and win32com is not None:
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

        for loc in locations:
            if loc.exists():
                for shortcut in loc.rglob("*.lnk"):
                    if "chrome" in shortcut.name.lower():
                        shell.CreateShortcut(str(shortcut))
                        return shortcut
        return None

    if sys.platform == "darwin":
        for script in _mac_shortcut_paths():
            if script.exists():
                return script
        return None

    for path in LINUX_PATHS:
        if path.exists():
            return path
    return None


if __name__ == "__main__":  # pragma: no cover - manual usage
    sys.exit(0 if update_chrome_shortcuts() else 1)
