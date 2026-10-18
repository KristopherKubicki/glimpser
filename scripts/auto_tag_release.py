import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION_FILE = Path("pyproject.toml")


def get_version(path: Path | None = None) -> str:
    """Read project.version, independently of formatting and tool versions."""
    data = tomllib.loads((path or VERSION_FILE).read_text())
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version or any(c.isspace() for c in version):
        raise RuntimeError("Missing or invalid project.version in pyproject.toml")
    return version


def tag_exists(tag):
    result = subprocess.run(
        [
            "git",
            "tag",
            "-l",
            tag,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return tag in result.stdout.split()


def create_tag(tag):
    subprocess.check_call(["git", "tag", tag])
    subprocess.check_call(["git", "push", "origin", tag])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tag the project's release version")
    parser.add_argument("--print-version", action="store_true")
    parser.add_argument("--version-file", type=Path, default=VERSION_FILE)
    args = parser.parse_args(argv)
    version = get_version(args.version_file)
    if args.print_version:
        print(version)
        return

    tag = f"v{version}"
    if tag_exists(tag):
        print(f"Tag {tag} already exists")
        return
    create_tag(tag)


if __name__ == "__main__":
    sys.exit(main())
