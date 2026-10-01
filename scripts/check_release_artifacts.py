"""Reject runtime state and dependency caches in Python release archives."""

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def check_archive(path: Path) -> int:
    """Validate member names without extracting untrusted archive content."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    for name in names:
        member = PurePosixPath(name)
        if (
            any(
                part in {"data", "logs", "node_modules", "__pycache__", ".hypothesis"}
                for part in member.parts
            )
            or member.name == ".env"
            or member.suffix in {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".pyc"}
            or ".session-secret" in member.name
            or ".db." in member.name
            or "private-migration" in member.name
        ):
            raise ValueError(f"Forbidden runtime member in {path.name}: {name}")
    return len(names)


if __name__ == "__main__":
    if not sys.argv[1:]:
        raise SystemExit("Provide at least one archive")
    for value in sys.argv[1:]:
        path = Path(value)
        print(f"{path.name}: checked {check_archive(path)} members")
