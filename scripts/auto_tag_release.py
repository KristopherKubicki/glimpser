import re
import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path("pyproject.toml")


def get_version() -> str:
    """Return the version string from pyproject.toml."""

    content = VERSION_FILE.read_text()
    match = re.search(r'^version = "(?P<ver>[^"]+)"', content, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Version not found in pyproject.toml")
    return match.group("ver")


def tag_exists(tag):
    result = subprocess.run(["git", "tag", "-l", tag], capture_output=True, text=True)
    return tag in result.stdout.split()


def create_tag(tag):
    subprocess.check_call(["git", "tag", tag])
    subprocess.check_call(["git", "push", "origin", tag])


def main():
    version = get_version()
    tag = f"v{version}"
    if tag_exists(tag):
        print(f"Tag {tag} already exists")
        return
    create_tag(tag)


if __name__ == "__main__":
    sys.exit(main())
