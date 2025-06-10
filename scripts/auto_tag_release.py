import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path("setup.py")


def get_version():
    for line in VERSION_FILE.read_text().splitlines():
        if "version=" in line:
            return line.split('"')[1]
    raise RuntimeError("Version not found in setup.py")


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
