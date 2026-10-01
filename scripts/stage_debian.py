"""Stage application source and assets without local runtime state."""

import shutil
from pathlib import Path

SOURCE_SUFFIXES = {
    ".py",
    ".html",
    ".css",
    ".js",
    ".json",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".txt",
}
ROOT_FILES = (
    "main.py",
    "generate_credentials.py",
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "LICENSE.md",
)


def stage_application(source: Path, destination: Path) -> None:
    """Copy a source allowlist into a new staging directory; never copy data/."""
    destination.mkdir(parents=True, exist_ok=False)
    for name in ROOT_FILES:
        path = source / name
        if path.is_symlink():
            raise ValueError(f"Refusing symlink in package source: {name}")
        shutil.copyfile(path, destination / name)
    for directory in ("app", "scripts"):
        for path in (source / directory).rglob("*"):
            relative = path.relative_to(source)
            if any(
                part.startswith(".") or part == "__pycache__" for part in relative.parts
            ):
                continue
            if path.is_symlink():
                raise ValueError(f"Refusing symlink in package source: {relative}")
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


if __name__ == "__main__":
    import sys

    stage_application(Path(sys.argv[1]), Path(sys.argv[2]))
